"""API Gateway (HTTP API, Lambda proxy integration) handler serving IOC data to the frontend.

Routes (v1 scope):
  GET /iocs            -> list recent IOCs (optionally filtered by ?type=ip|domain|url|hash|cve)
  GET /iocs/{ioc_id}    -> a single IOC by id

Uses the type-time-index GSI (see infra/dynamodb.tf) instead of a table scan: a single
Query when ?type= is given, or one Query per known type (merged, most-recent-first)
when it's omitted. Doesn't import common.schema's IOCType to avoid depending on the
ingestion Lambda layer for 5 constant strings - this function stays independently
deployable.
"""
from __future__ import annotations

import json
import os

import boto3
from boto3.dynamodb.conditions import Key

_dynamodb = boto3.resource("dynamodb")

_IOC_TYPES = ["ip", "domain", "url", "hash", "cve"]
_QUERY_LIMIT = 100


def _response(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body),
    }


def _query_type(table, ioc_type: str) -> list[dict]:
    result = table.query(
        IndexName="type-time-index",
        KeyConditionExpression=Key("ioc_type").eq(ioc_type),
        ScanIndexForward=False,  # most recent first
        Limit=_QUERY_LIMIT,
    )
    return result.get("Items", [])


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

    if ioc_type:
        items = _query_type(table, ioc_type)
    else:
        items = [item for t in _IOC_TYPES for item in _query_type(table, t)]
        items.sort(key=lambda i: i.get("ingested_at", 0), reverse=True)

    return _response(200, {"items": items})
