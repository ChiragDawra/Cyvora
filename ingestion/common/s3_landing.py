"""Shared helper for writing a feed's raw pull to the S3 landing bucket."""
from __future__ import annotations

import json
import os
import time

import boto3

_s3 = boto3.client("s3")


def write_raw(feed_name: str, payload: dict | list) -> str:
    """Writes payload as JSON to s3://LANDING_BUCKET/<feed_name>/<epoch>.json and returns the key."""
    bucket = os.environ["LANDING_BUCKET"]
    key = f"{feed_name}/{int(time.time())}.json"
    _s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(payload).encode("utf-8"))
    return key
