"""Shared helper for writing a feed's raw pull to the S3 landing bucket."""
from __future__ import annotations

import hashlib
import json
import os
import time

import boto3

from common.feed_state import get_state, put_state

_s3 = boto3.client("s3")


# Longest a feed may go without re-landing, even if its payload never changes. See the
# stuck-feed reasoning in write_raw.
MAX_SKIP_SECONDS = 24 * 60 * 60


def write_raw(feed_name: str, payload: dict | list) -> str | None:
    """Lands payload as JSON at s3://LANDING_BUCKET/<feed_name>/<epoch>.json.

    Returns the key written, or None when the payload is byte-identical to the previous
    pull AND that pull was recent. Skipping unchanged payloads avoids landing a duplicate
    object, which would re-trigger the normalizer and burn S3 storage for nothing - Feodo
    in particular can go hours without changing.

    The age check exists because the hash is recorded here, at land time, not after the
    normalizer succeeds. If normalization fails, the feed would otherwise stay stuck until
    the upstream payload happened to change - which for a 5-entry blocklist like Feodo
    could be days. Re-landing at least daily bounds that to 24 hours, at a cost of one
    extra object per feed per day.
    """
    bucket = os.environ["LANDING_BUCKET"]
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    now = int(time.time())

    previous = get_state(f"{feed_name}.sha256") or {}
    unchanged = previous.get("sha256") == digest
    fresh = now - previous.get("landed_at", 0) < MAX_SKIP_SECONDS
    if unchanged and fresh:
        return None

    key = f"{feed_name}/{now}.json"
    _s3.put_object(Bucket=bucket, Key=key, Body=body)
    put_state(f"{feed_name}.sha256", {"sha256": digest, "key": key, "landed_at": now})
    return key
