import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import unquote_plus

import boto3

DYNAMODB_TABLE = "earthquakes"
GSI_NAME = os.environ.get("GSI_NAME", "earthquake_id-index")

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(DYNAMODB_TABLE)


def _utc_iso_from_ms(ms_value):
    dt = datetime.fromtimestamp(ms_value / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_decimal(value):
    return Decimal(str(value))


def _valid_coordinates(coords):
    if not isinstance(coords, (list, tuple)) or len(coords) < 3:
        return False
    try:
        longitude = float(coords[0])
        latitude = float(coords[1])
        _ = float(coords[2])
    except (TypeError, ValueError):
        return False
    if latitude < -90 or latitude > 90:
        return False
    if longitude < -180 or longitude > 180:
        return False
    return True


def _extract_item(feature):
    if not isinstance(feature, dict):
        return None

    props = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coords = geometry.get("coordinates")

    if props.get("mag") is None:
        return None
    if props.get("type") != "earthquake":
        return None
    if not _valid_coordinates(coords):
        return None

    try:
        earthquake_id = feature["id"]
        magnitude = _to_decimal(props["mag"])
        time_ms = props["time"]
        time_iso = _utc_iso_from_ms(time_ms)
        longitude = _to_decimal(coords[0])
        latitude = _to_decimal(coords[1])
        depth_km = _to_decimal(coords[2])
    except (KeyError, TypeError, ValueError, IndexError):
        return None

    item = {
        "PK": "EQ",
        "SK": f"{time_iso}#{earthquake_id}",
        "earthquake_id": str(earthquake_id),
        "magnitude": magnitude,
        "mag_type": props.get("magType"),
        "place": props.get("place"),
        "time": _to_decimal(time_ms),
        "time_iso": time_iso,
        "latitude": latitude,
        "longitude": longitude,
        "depth_km": depth_km,
        "tsunami": _to_decimal(props.get("tsunami", 0)),
        "significance": _to_decimal(props.get("sig", 0)),
        "status": props.get("status"),
        "url": props.get("url"),
    }
    return item


def lambda_handler(event, context):
    records = event.get("Records", []) if isinstance(event, dict) else []
    if not records:
        print("process received no records")
        return {"ok": False, "written": 0, "skipped": 0}

    written = 0
    skipped = 0
    total_features = 0

    for record in records:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])

        if not key.startswith("raw/"):
            print(f"skipping non-raw object bucket={bucket} key={key}")
            continue

        obj = s3.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read().decode("utf-8")
        payload = json.loads(body)
        features = payload.get("features", []) if isinstance(payload, dict) else []
        if not isinstance(features, list):
            features = []

        total_features += len(features)

        for feature in features:
            item = _extract_item(feature)
            if item is None:
                skipped += 1
                continue
            table.put_item(Item=item)
            written += 1

    print(
        f"process completed files={len(records)} features={total_features} written={written} skipped={skipped} gsi={GSI_NAME}"
    )
    return {"ok": True, "written": written, "skipped": skipped, "features": total_features}
