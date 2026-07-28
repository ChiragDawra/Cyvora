"""Pulls the Feodo Tracker botnet C2 IP blocklist and lands the raw JSON in S3.

Same abuse.ch Auth-Key requirement and rate-limit etiquette as urlhaus/handler.py.

TODO before first real run: verify the exact endpoint against the current abuse.ch
Feodo Tracker API docs.
"""
from __future__ import annotations

import os

import requests

from common.s3_landing import write_raw

FEODO_BLOCKLIST_URL = "https://feodotracker.abuse.ch/downloads/ipblocklist.json"


def lambda_handler(event, context):
    auth_key = os.environ["ABUSECH_AUTH_KEY"]
    resp = requests.get(FEODO_BLOCKLIST_URL, headers={"Auth-Key": auth_key}, timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    key = write_raw("feodo", payload)
    # key is None when the payload is unchanged since the last pull - see write_raw.
    return {"feed": "feodo", "landed_key": key, "skipped_unchanged": key is None}
