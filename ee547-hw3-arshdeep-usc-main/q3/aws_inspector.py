import boto3
import json
import sys
import argparse
from datetime import datetime, timezone
from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError

# ==========================================================
# Utility Helpers
# ==========================================================

def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_iso(dt):
    if not dt:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def retry_once(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except EndpointConnectionError:
        print("[WARNING] Network timeout. Retrying once...")
        return func(*args, **kwargs)


def resolve_region(cli_region):
    session = boto3.session.Session()
    region = cli_region or session.region_name

    if not region:
        print("[ERROR] No region specified. Use --region or configure AWS CLI.")
        sys.exit(1)

    return region


def verify_auth():
    try:
        sts = boto3.client("sts")
        return sts.get_caller_identity()
    except NoCredentialsError:
        print("[ERROR] AWS credentials not found.")
        sys.exit(1)
    except ClientError as e:
        print(f"[ERROR] Authentication failed: {e}")
        sys.exit(1)


# ==========================================================
# IAM USERS
# ==========================================================

def collect_iam_users():
    iam = boto3.client("iam")
    results = []

    try:
        users = retry_once(iam.list_users)["Users"]
    except ClientError:
        print("[WARNING] Access denied for IAM operations - skipping user enumeration")
        return []

    for user in users:
        username = user["UserName"]

        try:
            policies = iam.list_attached_user_policies(UserName=username)["AttachedPolicies"]
        except ClientError:
            policies = []

        results.append({
            "username": username,
            "user_id": user["UserId"],
            "arn": user["Arn"],
            "create_date": to_iso(user["CreateDate"]),
            "last_activity": to_iso(user.get("PasswordLastUsed")),
            "attached_policies": [
                {"policy_name": p["PolicyName"], "policy_arn": p["PolicyArn"]} for p in policies
            ]
        })

    return results


# ==========================================================
# EC2 INSTANCES
# ==========================================================

def collect_ec2_instances(region):
    ec2 = boto3.client("ec2", region_name=region)
    results = []

    try:
        reservations = retry_once(ec2.describe_instances)["Reservations"]
    except ClientError:
        print("[WARNING] Access denied for EC2 operations - skipping instances")
        return []

    if not reservations:
        print(f"[WARNING] No EC2 instances found in {region}")

    for reservation in reservations:
        for instance in reservation["Instances"]:
            ami_name = None
            try:
                images = ec2.describe_images(ImageIds=[instance["ImageId"]])["Images"]
                if images:
                    ami_name = images[0].get("Name")
            except ClientError:
                pass

            results.append({
                "instance_id": instance["InstanceId"],
                "instance_type": instance["InstanceType"],
                "state": instance["State"]["Name"],
                "public_ip": instance.get("PublicIpAddress"),
                "private_ip": instance.get("PrivateIpAddress"),
                "availability_zone": instance["Placement"]["AvailabilityZone"],
                "launch_time": to_iso(instance["LaunchTime"]),
                "ami_id": instance["ImageId"],
                "ami_name": ami_name,
                "security_groups": [sg["GroupId"] for sg in instance.get("SecurityGroups", [])],
                "tags": {t["Key"]: t["Value"] for t in instance.get("Tags", [])}
            })

    return results


# ==========================================================
# S3 BUCKETS
# ==========================================================

def collect_s3_buckets():
    s3 = boto3.client("s3")
    session = boto3.session.Session()
    default_region = session.region_name or "us-east-1"
    results = []

    try:
        buckets = retry_once(s3.list_buckets)["Buckets"]
    except ClientError:
        print("[WARNING] Access denied for S3 operations - skipping buckets")
        return []

    for bucket in buckets:
        name = bucket["Name"]

        try:
            location = s3.get_bucket_location(Bucket=name)["LocationConstraint"]
            region = location if location else default_region

            object_count = 0
            size_bytes = 0
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=name):
                for obj in page.get("Contents", []):
                    object_count += 1
                    size_bytes += obj["Size"]

        except ClientError as e:
            print(f"[ERROR] Failed to access S3 bucket '{name}': {e.response['Error']['Message']}")
            continue

        results.append({
            "bucket_name": name,
            "creation_date": to_iso(bucket["CreationDate"]),
            "region": region,
            "object_count": object_count,
            "size_bytes": size_bytes
        })

    return results


# ==========================================================
# SECURITY GROUPS
# ==========================================================

def parse_rules(rules, inbound=True):
    parsed = []
    for rule in rules:
        protocol = rule.get("IpProtocol")
        if protocol == "-1":
            protocol = "all"

        from_port = rule.get("FromPort")
        to_port = rule.get("ToPort")

        if protocol == "all" or from_port is None:
            port_range = "all"
        else:
            port_range = f"{from_port}-{to_port}"

        key = "source" if inbound else "destination"

        for ip_range in rule.get("IpRanges", []):
            parsed.append({
                "protocol": protocol,
                "port_range": port_range,
                key: ip_range["CidrIp"]
            })

    return parsed


def collect_security_groups(region):
    ec2 = boto3.client("ec2", region_name=region)
    results = []

    try:
        groups = retry_once(ec2.describe_security_groups)["SecurityGroups"]
    except ClientError:
        print("[WARNING] Access denied for Security Group operations - skipping")
        return []

    for group in groups:
        results.append({
            "group_id": group["GroupId"],
            "group_name": group["GroupName"],
            "description": group["Description"],
            "vpc_id": group.get("VpcId"),
            "inbound_rules": parse_rules(group.get("IpPermissions", []), True),
            "outbound_rules": parse_rules(group.get("IpPermissionsEgress", []), False)
        })

    return results


# ==========================================================
# TABLE OUTPUT
# ==========================================================

def print_table(report):
    info = report["account_info"]
    resources = report["resources"]
    summary = report["summary"]

    print(f"\nAWS Account: {info['account_id']} ({info['region']})")
    print(f"Scan Time: {info['scan_timestamp']}\n")

    # ---- IAM USERS ----
    print(f"IAM USERS ({summary['total_users']} total)")
    print(f"{'Username':20} {'Created':12} {'Last Active':12} Policies")
    for u in resources["iam_users"]:
        print(f"{u['username']:20} "
              f"{(u['create_date'] or '-')[:10]:12} "
              f"{(u['last_activity'] or '-')[:10]:12} "
              f"{len(u['attached_policies'])}")
    print()

    # ---- EC2 INSTANCES ----
    running = sum(1 for i in resources["ec2_instances"] if i["state"] == "running")
    stopped = sum(1 for i in resources["ec2_instances"] if i["state"] == "stopped")
    print(f"EC2 INSTANCES ({running} running, {stopped} stopped)")
    print(f"{'Instance ID':20} {'Type':10} {'State':10} {'Public IP':15} {'Launch Time':16}")
    for i in resources["ec2_instances"]:
        launch_time_str = "-"
        if i.get("launch_time"):
            dt = datetime.strptime(i["launch_time"], "%Y-%m-%dT%H:%M:%SZ")
            launch_time_str = dt.strftime("%Y-%m-%d %H:%M")
        print(f"{i['instance_id']:20} "
              f"{i['instance_type']:10} "
              f"{i['state']:10} "
              f"{i['public_ip'] or '-':15} "
              f"{launch_time_str:16}")
    print()

    # ---- S3 BUCKETS ----
    print(f"S3 BUCKETS ({summary['total_buckets']} total)")
    print(f"{'Bucket Name':25} {'Region':12} {'Created':12} {'Objects':8} Size(MB)")
    for b in resources["s3_buckets"]:
        size_mb = round(b["size_bytes"] / (1024 * 1024), 1)
        created_str = b["creation_date"][:10] if b.get("creation_date") else "-"
        print(f"{b['bucket_name']:25} {b['region']:12} "
              f"{created_str:12} {b['object_count']:8} ~{size_mb}")
    print()

    # ---- SECURITY GROUPS ----
    print(f"SECURITY GROUPS ({summary['security_groups']} total)")
    print(f"{'Group ID':15} {'Name':15} {'VPC ID':15} Inbound Rules")
    for g in resources["security_groups"]:
        print(f"{g['group_id']:15} "
              f"{g['group_name']:15} "
              f"{g['vpc_id'] or '-':15} "
              f"{len(g['inbound_rules'])}")
    print()


# ==========================================================
# MAIN
# ==========================================================

def main():
    parser = argparse.ArgumentParser(description="AWS Resource Inspector")
    parser.add_argument("--region", help="AWS region to inspect")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--format", choices=["json", "table"], default="json")
    args = parser.parse_args()

    region = resolve_region(args.region)
    identity = verify_auth()

    iam_users = collect_iam_users()
    ec2_instances = collect_ec2_instances(region)
    s3_buckets = collect_s3_buckets()
    security_groups = collect_security_groups(region)

    report = {
        "account_info": {
            "account_id": identity["Account"],
            "user_arn": identity["Arn"],
            "region": region,
            "scan_timestamp": utc_now()
        },
        "resources": {
            "iam_users": iam_users,
            "ec2_instances": ec2_instances,
            "s3_buckets": s3_buckets,
            "security_groups": security_groups
        },
        "summary": {
            "total_users": len(iam_users),
            "running_instances": sum(1 for i in ec2_instances if i["state"] == "running"),
            "total_buckets": len(s3_buckets),
            "security_groups": len(security_groups)
        }
    }

    if args.format == "json":
        output = json.dumps(report, indent=4)
        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
        else:
            print(output)
    else:
        print_table(report)


if __name__ == "__main__":
    main()