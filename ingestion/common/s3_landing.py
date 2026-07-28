"""Shared helper for writing a feed's raw pull to the S3 landing bucket."""
from __future__ import annotations

import hashlib
import json
import os
import time

import boto3

from common.feed_state import get_state, put_state

_s3 = boto3.client("s3")


def write_raw(feed_name: str, payload: dict | list) -> str | None:
    """Lands payload as JSON at s3://LANDING_BUCKET/<feed_name>/<epoch>.json.

    Returns the key written, or None when the payload is byte-identical to the previous
    pull. Skipping unchanged payloads avoids landing a duplicate object, which would
    re-trigger the normalizer and burn S3 storage for nothing - Feodo in particular can
    go hours without changing.
    """
    bucket = os.environ["LANDING_BUCKET"]
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()

    previous = get_state(f"{feed_name}.sha256") or {}
    if previous.get("sha256") == digest:
        return None

    key = f"{feed_name}/{int(time.time())}.json"
    _s3.put_object(Bucket=bucket, Key=key, Body=body)
    put_state(f"{feed_name}.sha256", {"sha256": digest, "key": key})
    return key
