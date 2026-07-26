"""Enriches a small, filtered subset of already-ingested IP IOCs via AbuseIPDB.

AbuseIPDB free tier is 1,000 checks/day — this must NEVER be called per-IOC across the
whole dataset. MAX_IPS_PER_RUN caps each invocation; tune the schedule/cap so daily
usage stays comfortably under quota.

TODO before first real run: replace `_get_unenriched_ips` with a real query against the
IOC DynamoDB table (e.g. a GSI on `ioc_type=ip AND enriched=false`) - this stub just
shows the shape of the call.
"""
from __future__ import annotations

import os

import requests

from common.s3_landing import write_raw

ABUSEIPDB_CHECK_URL = "https://api.abuseipdb.com/api/v2/check"
MAX_IPS_PER_RUN = 50


def _get_unenriched_ips() -> list[str]:
    """Placeholder — wire this up to a real DynamoDB query in Phase 1."""
    return []


def lambda_handler(event, context):
    api_key = os.environ["ABUSEIPDB_API_KEY"]
    ips = _get_unenriched_ips()[:MAX_IPS_PER_RUN]

    results = []
    for ip in ips:
        resp = requests.get(
            ABUSEIPDB_CHECK_URL,
            headers={"Key": api_key, "Accept": "application/json"},
            params={"ipAddress": ip, "maxAgeInDays": 90},
            timeout=15,
        )
        resp.raise_for_status()
        results.append(resp.json())

    key = write_raw("abuseipdb_enrich", results) if results else None
    return {"feed": "abuseipdb_enrich", "enriched_count": len(results), "landed_key": key}
