"""API Gateway (HTTP API, Lambda proxy integration) handler serving IOC data to the frontend.

Routes (v1 scope):
  GET /iocs            -> list recent IOCs (optionally filtered by ?type=ip|domain|url|hash|cve)
  GET /iocs/{ioc_id}    -> a single IOC by id

TODO before first real run: swap the bare `scan` for a proper query using the table's
GSIs (time/geo) once the Terraform-provisioned table + indexes exist — a full table
scan does not scale past the MVP demo dataset.
"""
from __future__ import annotations

import json
import os

import boto3

_dynamodb = boto3.resource("dynamodb")


def _response(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body),
    }


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

    scan_kwargs = {}
    if ioc_type:
        scan_kwargs["FilterExpression"] = boto3.dynamodb.conditions.Attr("ioc_type").eq(ioc_type)

    result = table.scan(**scan_kwargs)
    return _response(200, {"items": result.get("Items", [])})
