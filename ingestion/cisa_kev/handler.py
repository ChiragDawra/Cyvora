"""Pulls the CISA Known Exploited Vulnerabilities catalog and lands the raw JSON in S3.

Fully free, no key, no auth. CISA adds entries irregularly (several times/week) —
polling once daily and diffing against the previous pull is sufficient.
"""
from __future__ import annotations

import requests

from common.s3_landing import write_raw

CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"


def lambda_handler(event, context):
    resp = requests.get(CISA_KEV_URL, timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    key = write_raw("cisa_kev", payload)
    # key is None when the payload is unchanged since the last pull - see write_raw.
    return {"feed": "cisa_kev", "landed_key": key, "skipped_unchanged": key is None}
