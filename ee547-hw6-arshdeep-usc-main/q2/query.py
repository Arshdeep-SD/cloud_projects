import json
import os
from datetime import datetime, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "earthquakes")
GSI_NAME = os.environ.get("GSI_NAME", "earthquake_id-index")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(DYNAMODB_TABLE)


def _json_default(value):
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _response(status_code, payload):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, default=_json_default),
    }


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d")


def _date_bounds(start_date, end_date):
    start_iso = f"{start_date.strftime('%Y-%m-%d')}T00:00:00Z"
    end_next_day = end_date + timedelta(days=1)
    end_iso = f"{end_next_day.strftime('%Y-%m-%d')}T00:00:00Z"
    return start_iso, end_iso


def _compact_item(item):
    return {
        "earthquake_id": item.get("earthquake_id"),
        "magnitude": item.get("magnitude"),
        "place": item.get("place"),
        "time": item.get("time_iso"),
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
        "depth_km": item.get("depth_km"),
    }


def _full_item(item):
    return {
        "earthquake_id": item.get("earthquake_id"),
        "magnitude": item.get("magnitude"),
        "mag_type": item.get("mag_type"),
        "place": item.get("place"),
        "time": item.get("time_iso"),
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
        "depth_km": item.get("depth_km"),
        "tsunami": item.get("tsunami"),
        "significance": item.get("significance"),
        "status": item.get("status"),
        "url": item.get("url"),
    }


def _list_earthquakes(params):
    start = params.get("start")
    end = params.get("end")

    if not start or not end:
        return _response(400, {"error": "start and end are required"})

    try:
        start_date = _parse_date(start)
        end_date = _parse_date(end)
    except ValueError:
        return _response(400, {"error": "start and end must use YYYY-MM-DD format"})

    if end_date < start_date:
        return _response(400, {"error": "end must be on or after start"})

    try:
        min_magnitude = float(params.get("min_magnitude", 0))
    except (TypeError, ValueError):
        return _response(400, {"error": "min_magnitude must be numeric"})

    try:
        limit = int(params.get("limit", 50))
    except (TypeError, ValueError):
        return _response(400, {"error": "limit must be an integer"})

    if limit < 1:
        limit = 1
    if limit > 500:
        limit = 500

    start_key, end_key = _date_bounds(start_date, end_date)

    items = []
    last_key = None

    while len(items) < limit:
        query_kwargs = {
            "KeyConditionExpression": Key("PK").eq("EQ") & Key("SK").between(start_key, end_key),
            "ScanIndexForward": False,
            "Limit": 100,
        }
        if last_key:
            query_kwargs["ExclusiveStartKey"] = last_key

        response = table.query(**query_kwargs)

        for raw_item in response.get("Items", []):
            try:
                magnitude_value = float(raw_item.get("magnitude"))
            except (TypeError, ValueError):
                continue

            if magnitude_value >= min_magnitude:
                items.append(_compact_item(raw_item))
                if len(items) >= limit:
                    break

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

    payload = {
        "parameters": {
            "start": start,
            "end": end,
            "min_magnitude": min_magnitude,
            "limit": limit,
        },
        "earthquakes": items,
        "count": len(items),
    }
    return _response(200, payload)


def _get_earthquake(earthquake_id):
    response = table.query(
        IndexName=GSI_NAME,
        KeyConditionExpression=Key("earthquake_id").eq(earthquake_id),
        Limit=1,
    )

    items = response.get("Items", [])
    if not items:
        return _response(404, {"error": "Earthquake not found", "earthquake_id": earthquake_id})

    return _response(200, _full_item(items[0]))


def lambda_handler(event, context):
    try:
        raw_path = event.get("rawPath", "") if isinstance(event, dict) else ""
        path_parameters = event.get("pathParameters") or {}
        query_parameters = event.get("queryStringParameters") or {}

        parts = [part for part in raw_path.split("/") if part]

        if len(parts) == 1 and parts[0] == "earthquakes":
            return _list_earthquakes(query_parameters)

        if len(parts) == 2 and parts[0] == "earthquakes":
            earthquake_id = path_parameters.get("earthquake_id") or parts[1]
            if not earthquake_id:
                return _response(400, {"error": "earthquake_id is required"})
            return _get_earthquake(earthquake_id)

        return _response(404, {"error": "Not found"})

    except Exception as exc:
        print(f"query failed error={exc}")
        return _response(500, {"error": "Internal server error"})