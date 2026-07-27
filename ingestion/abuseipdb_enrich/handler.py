"""Enriches a small, filtered subset of already-ingested IP IOCs via AbuseIPDB, then
writes the confidence score + approximate country-level geo back onto each IOC's
DynamoDB item so the API/frontend can plot it.

AbuseIPDB free tier is 1,000 checks/day — this must NEVER be called per-IOC across the
whole dataset. MAX_IPS_PER_RUN caps each invocation; the daily schedule (see
infra/eventbridge.tf) keeps usage far under quota even at that cap.

`_get_unenriched_ips` uses a table `scan` with a filter, not a GSI query - there's no
index on "missing confidence attribute" (DynamoDB doesn't support that), and this is a
low-frequency (daily), Limit-bounded operation. Fine at MVP scale; revisit if the table
grows large enough for scans to get slow/expensive.
"""
from __future__ import annotations

import os

import boto3
import requests
from boto3.dynamodb.conditions import Attr

from common.geo import country_centroid
from common.schema import IOC, IOCType

ABUSEIPDB_CHECK_URL = "https://api.abuseipdb.com/api/v2/check"
MAX_IPS_PER_RUN = 50

_dynamodb = boto3.resource("dynamodb")


def _get_unenriched_ips(table) -> list[str]:
    result = table.scan(
        FilterExpression=Attr("ioc_type").eq("ip") & Attr("confidence").not_exists(),
        ProjectionExpression="#v",
        ExpressionAttributeNames={"#v": "value"},
        Limit=MAX_IPS_PER_RUN,
    )
    return [item["value"] for item in result.get("Items", [])]


def lambda_handler(event, context):
    api_key = os.environ["ABUSEIPDB_API_KEY"]
    table = _dynamodb.Table(os.environ["IOC_TABLE"])

    ips = _get_unenriched_ips(table)
    enriched = 0

    for ip in ips:
        resp = requests.get(
            ABUSEIPDB_CHECK_URL,
            headers={"Key": api_key, "Accept": "application/json"},
            params={"ipAddress": ip, "maxAgeInDays": 90},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})

        ioc_id = IOC(ioc_type=IOCType.IP, value=ip, source_feed="", first_seen="", last_seen="").ioc_id
        geo = country_centroid(data.get("countryCode"))

        update_expr = "SET confidence = :c"
        expr_values = {":c": data.get("abuseConfidenceScore", 0)}
        if geo is not None:
            update_expr += ", geo = :g"
            expr_values[":g"] = geo

        table.update_item(
            Key={"ioc_id": ioc_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
        )
        enriched += 1

    return {"feed": "abuseipdb_enrich", "enriched_count": enriched}
