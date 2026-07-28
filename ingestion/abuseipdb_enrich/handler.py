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

# One API call per IP, one run per day (see infra/eventbridge.tf), free tier is 1,000
# checks/day - so 400 leaves a wide margin while still filling the map reasonably fast.
MAX_IPS_PER_RUN = 400
SCAN_PAGE_SIZE = 200
MAX_SCAN_PAGES = 20

_dynamodb = boto3.resource("dynamodb")


def _get_unenriched_ips(table) -> list[str]:
    """Collects up to MAX_IPS_PER_RUN IPs that have no confidence score yet.

    DynamoDB applies `Limit` to items *scanned*, before the FilterExpression runs - so
    passing Limit=MAX_IPS_PER_RUN in a single call reads 50 arbitrary items and then
    filters them down, usually to zero. The scan has to be paginated and stopped once
    enough *matching* items are found instead.

    SCAN_PAGE_SIZE bounds each page so a large table can't burn the table's provisioned
    read capacity (see infra/dynamodb.tf) in one go, and MAX_SCAN_PAGES bounds the total
    work per daily run.
    """
    ips: list[str] = []
    kwargs = {
        "FilterExpression": Attr("ioc_type").eq("ip") & Attr("confidence").not_exists(),
        "ProjectionExpression": "#v",
        "ExpressionAttributeNames": {"#v": "value"},
        "Limit": SCAN_PAGE_SIZE,
    }

    for _ in range(MAX_SCAN_PAGES):
        result = table.scan(**kwargs)
        for item in result.get("Items", []):
            ips.append(item["value"])
            if len(ips) >= MAX_IPS_PER_RUN:
                return ips

        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key

    return ips


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
        # 429 means the free-tier daily quota is gone. Stop cleanly and pick up where we
        # left off tomorrow - raising here would trip the Lambda error alarm for what is
        # a completely expected condition.
        if resp.status_code == 429:
            break
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
