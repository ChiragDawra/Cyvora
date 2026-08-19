"""Pulls indicators from the AlienVault OTX pulses this account subscribes to.

Needs a free OTX API key (otx.alienvault.com, Settings > OTX API) and at least one
subscribed pulse: /pulses/subscribed returns only what the account follows, so a fresh
account with no subscriptions gets an empty result set rather than an error. That is a
silent no-op, which is why the return value reports the pulse count.

Deliberately NOT using the endpoint's `modified_since` parameter, even though it would
shrink each pull. The same reasoning as the 24-hour re-land in common/s3_landing.py
applies: any progress marker advanced here, at pull time, is advanced before the
normalizer has confirmed it wrote anything, so a normalization failure would silently
drop those indicators for good. Full pulls plus the normalizer's watermark cost one
extra S3 object and no extra DynamoDB writes.

Field names confirmed against a live authenticated pull on 2026-08-19: 100 pulses,
2,816 indicators, 817 KB landed, parsed with zero failures.

That pull returned exactly PAGE_SIZE * MAX_PAGES pulses, meaning the cap was reached and
older subscribed pulses were left behind. That is the intended tradeoff - results come
back most-recently-modified first, so what gets dropped is the stalest - but it does mean
the feed is a recency window, not a complete mirror of everything the account follows.
Raise MAX_PAGES if that stops being good enough, and watch the landed object size.
"""
from __future__ import annotations

import os

import requests

from common.s3_landing import write_raw

OTX_SUBSCRIBED_URL = "https://otx.alienvault.com/api/v1/pulses/subscribed"

# Pulses carry their indicators inline, and a single well-populated pulse can hold
# thousands. 20 x 5 bounds one pull to ~100 pulses, which keeps the landed object at a
# sane size and the Lambda well inside its timeout. Results come back most-recently-
# modified first, so the cap drops the stalest pulses, not the freshest.
PAGE_SIZE = 20
MAX_PAGES = 5


def _fetch_pulses(api_key: str) -> list[dict]:
    pulses: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        resp = requests.get(
            OTX_SUBSCRIBED_URL,
            headers={"X-OTX-API-Key": api_key},
            params={"limit": PAGE_SIZE, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()

        results = body.get("results", [])
        pulses.extend(results)

        # A short page means this was the last one; `next` being null says the same thing
        # and is the documented signal, so honour whichever arrives first.
        if len(results) < PAGE_SIZE or not body.get("next"):
            break

    return pulses


def lambda_handler(event, context):
    api_key = os.environ["OTX_API_KEY"]
    pulses = _fetch_pulses(api_key)

    # Wrapped in a dict rather than landed as a bare list so the shape stays stable if
    # this ever needs to carry pull metadata alongside the pulses.
    key = write_raw("otx", {"pulses": pulses})
    # key is None when the payload is unchanged since the last pull - see write_raw.
    return {
        "feed": "otx",
        "pulses": len(pulses),
        "landed_key": key,
        "skipped_unchanged": key is None,
    }
