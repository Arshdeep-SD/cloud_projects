import json
import os
import urllib.request
from datetime import datetime, timezone

import boto3

S3_BUCKET = "earthquakes-ee547-hw6"
FEED_URL = os.environ.get(
    "FEED_URL",
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson",
)

s3 = boto3.client("s3")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


def lambda_handler(event, context):
    timestamp = _utc_timestamp()
    try:
        request = urllib.request.Request(
            FEED_URL,
            headers={"User-Agent": "aws-lambda-earthquake-pipeline"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                print(f"fetch failed timestamp={timestamp} status={status} url={FEED_URL}")
                return {"ok": False, "statusCode": status}

            raw_bytes = response.read()
            raw_text = raw_bytes.decode("utf-8")
            payload = json.loads(raw_text)

    except Exception as exc:
        print(f"fetch failed timestamp={timestamp} url={FEED_URL} error={exc}")
        return {"ok": False, "error": str(exc)}

    features = payload.get("features", []) if isinstance(payload, dict) else []
    feature_count = len(features) if isinstance(features, list) else 0
    key = f"raw/{timestamp}.json"

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=raw_bytes,
        ContentType="application/json",
    )

    print(
        f"fetch succeeded timestamp={timestamp} status=200 feature_count={feature_count} s3_key={key}"
    )
    return {"ok": True, "bucket": S3_BUCKET, "key": key, "feature_count": feature_count}
