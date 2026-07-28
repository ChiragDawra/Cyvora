"""Pulls recent URLhaus entries and lands the raw JSON in S3.

abuse.ch requires a free Auth-Key header as of June 2025 (sign up at auth.abuse.ch).
Poll no faster than every 5 minutes — URLhaus regenerates its dumps on that cadence.

TODO before first real run: verify the exact endpoint path/params against the current
abuse.ch URLhaus API docs — endpoints have shifted before and this stub has not been
run against the live API yet.
"""
from __future__ import annotations

import os

import requests

from common.s3_landing import write_raw

URLHAUS_RECENT_URL = "https://urlhaus-api.abuse.ch/v1/urls/recent/"


def lambda_handler(event, context):
    auth_key = os.environ["ABUSECH_AUTH_KEY"]
    resp = requests.get(URLHAUS_RECENT_URL, headers={"Auth-Key": auth_key}, timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    key = write_raw("urlhaus", payload)
    # key is None when the payload is unchanged since the last pull - see write_raw.
    return {"feed": "urlhaus", "landed_key": key, "skipped_unchanged": key is None}
