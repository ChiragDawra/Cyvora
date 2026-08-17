"""API Gateway (HTTP API, Lambda proxy integration) handler serving IOC data to the frontend.

Routes (v1 scope):
  GET /iocs            -> list recent IOCs (optionally filtered by ?type=ip|domain|url|hash|cve)
  GET /iocs/{ioc_id}    -> a single IOC by id

Uses the type-time-index GSI (see infra/dynamodb.tf) instead of a table scan: a single
Query when ?type= is given, or one Query per known type (merged, most-recent-first)
when it's omitted. Doesn't import common.schema's IOCType to avoid depending on the
ingestion Lambda layer for 5 constant strings - this function stays independently
deployable.

?geo=true switches to _query_type_geo: the daily AbuseIPDB enrichment job (which sets
`geo`) is capped well below ingestion volume, so the newest IOCs the plain query returns
almost never have it yet - the map/globe would render empty despite plenty of enriched
IOCs existing further back in time. _query_type_geo pages backward through the same
time-sorted GSI, filtering for `geo`, until it collects enough points or hits the page
cap - same "Limit applies before FilterExpression" pagination fix as
ingestion/abuseipdb_enrich/handler.py's _get_unenriched_ips.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr, Key

_dynamodb = boto3.resource("dynamodb")

_IOC_TYPES = ["ip", "domain", "url", "hash", "cve"]
_QUERY_LIMIT = 100
_GEO_PAGE_SIZE = 200
_GEO_MAX_PAGES = 10


def _json_default(value):
    """Makes DynamoDB's Decimal values JSON-serializable.

    boto3's DynamoDB resource layer returns every number as a Decimal, and json.dumps
    raises TypeError on those - which meant every response from this handler was a 500.

    Integral values go out as int so `ingested_at` stays a plain epoch rather than
    1.7852e9; everything else (geo lat/lon) becomes a float, which is what the frontend's
    map expects.
    """
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")


def _response(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body, default=_json_default),
    }


def _query_type(table, ioc_type: str) -> list[dict]:
    result = table.query(
        IndexName="type-time-index",
        KeyConditionExpression=Key("ioc_type").eq(ioc_type),
        ScanIndexForward=False,  # most recent first
        Limit=_QUERY_LIMIT,
    )
    return result.get("Items", [])


def _query_type_geo(table, ioc_type: str) -> list[dict]:
    items: list[dict] = []
    kwargs = {
        "IndexName": "type-time-index",
        "KeyConditionExpression": Key("ioc_type").eq(ioc_type),
        "FilterExpression": Attr("geo").exists(),
        "ScanIndexForward": False,
        "Limit": _GEO_PAGE_SIZE,
    }

    for _ in range(_GEO_MAX_PAGES):
        result = table.query(**kwargs)
        items.extend(result.get("Items", []))
        if len(items) >= _QUERY_LIMIT:
            return items[:_QUERY_LIMIT]

        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key

    return items


def lambda_handler(event, context):
    table = _dynamodb.Table(os.environ["IOC_TABLE"])

    path_params = event.get("pathParameters") or {}
    ioc_id = path_params.get("ioc_id")

    if ioc_id:
        result = table.get_item(Key={"ioc_id": ioc_id})
        item = result.get("Item")
        if item is None:
            return _response(404, {"error": "not found"})
        return _response(200, item)

    query_params = event.get("queryStringParameters") or {}
    ioc_type = query_params.get("type")
    geo_only = query_params.get("geo") in ("1", "true", "True")
    query_fn = _query_type_geo if geo_only else _query_type

    if ioc_type:
        items = query_fn(table, ioc_type)
    else:
        items = [item for t in _IOC_TYPES for item in query_fn(table, t)]
        items.sort(key=lambda i: i.get("ingested_at", 0), reverse=True)

    return _response(200, {"items": items})
