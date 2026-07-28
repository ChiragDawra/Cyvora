"""Tiny JSON state store on top of the landing bucket.

Two pieces of per-feed state live here:

- `<feed>.sha256` — hash of the last raw payload, so an unchanged feed doesn't get
  re-landed (see common/s3_landing.py).
- `<feed>.watermark` — the newest source timestamp already written to DynamoDB, so the
  normalizer only writes genuinely new records (see normalizer/handler.py).

Both live under `_state/`, which is deliberately NOT one of the feed prefixes wired to
the normalizer in infra/eventbridge.tf — writing state must not re-trigger the pipeline.

S3 rather than DynamoDB on purpose: these are a handful of sub-1KB objects read/written
once per feed per run, and keeping them off the table leaves the whole provisioned
capacity budget for real IOC writes.
"""
from __future__ import annotations

import json
import os

import boto3
from botocore.exceptions import ClientError

STATE_PREFIX = "_state/"

_s3 = boto3.client("s3")


def _bucket() -> str:
    return os.environ["LANDING_BUCKET"]


def get_state(name: str) -> dict | None:
    """Returns the stored state object, or None if it has never been written."""
    try:
        obj = _s3.get_object(Bucket=_bucket(), Key=f"{STATE_PREFIX}{name}.json")
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise
    return json.loads(obj["Body"].read())


def put_state(name: str, state: dict) -> None:
    _s3.put_object(
        Bucket=_bucket(),
        Key=f"{STATE_PREFIX}{name}.json",
        Body=json.dumps(state).encode("utf-8"),
    )
