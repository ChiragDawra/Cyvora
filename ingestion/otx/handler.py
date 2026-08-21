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
Raise MAX_PAGES if that stops being good enough, and watch the landed object size: the
same 100 pulses carried 2,816 indicators on 2026-08-19 and 7,482 on 2026-08-21, so the
per-pulse weight moves a lot. That growth is a size and duration concern, not a DynamoDB
one - the normalizer's watermark means a steady-state run writes almost none of it.

Timeouts and retries exist because of a measured failure, not caution. On 2026-08-21 the
daily run failed three times with `ReadTimeout ... (read timeout=30)`. Timing the same
request by hand: 34.3s, then 2.8s, then 0.6s for a byte-identical response. OTX serves
this endpoint from a cache that a cold request has to populate, so the first pull of the
day is an order of magnitude slower than every one after it - and the request that times
out is the one that warms it. That makes a retry unusually effective here: the attempt
that failed is what makes the next attempt fast.
"""
from __future__ import annotations

import os
import time
from typing import NamedTuple

import requests

from common.s3_landing import write_raw

OTX_SUBSCRIBED_URL = "https://otx.alienvault.com/api/v1/pulses/subscribed"

# Pulses carry their indicators inline, and a single well-populated pulse can hold
# thousands. 20 x 5 bounds one pull to ~100 pulses, which keeps the landed object at a
# sane size and the Lambda well inside its timeout. Results come back most-recently-
# modified first, so the cap drops the stalest pulses, not the freshest.
PAGE_SIZE = 20
MAX_PAGES = 5

# Split rather than a single number: a connect that hasn't completed in 5s is a network
# fault worth failing fast on, whereas a read legitimately takes ~35s on a cold cache.
# 45s gives that measured worst case real headroom without waiting out a dead socket.
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 45
MAX_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 2

# Seconds to keep in reserve for write_raw's S3 put and state write. Paging stops once
# the remaining Lambda time can't cover another full attempt plus this - being killed
# mid-request loses every page already fetched and logs no traceback at all, which is a
# strictly worse failure than stopping early and landing what we have.
TIME_RESERVE_SECONDS = 15


class Pull(NamedTuple):
    pulses: list[dict]
    pages_fetched: int
    # None when every page this pull intended to fetch came back; otherwise why it stopped.
    incomplete_reason: str | None


def _seconds_left(context) -> float:
    """Remaining Lambda execution time, or unlimited when run outside Lambda (tests,
    local invocation) where there is no deadline to respect."""
    if context is None or not hasattr(context, "get_remaining_time_in_millis"):
        return float("inf")
    return context.get_remaining_time_in_millis() / 1000.0


def _is_transient(exc: Exception) -> bool:
    """Retry transport faults and OTX asking us to back off; never retry a 401/403, which
    means the API key is wrong and will be just as wrong a second later."""
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


def _get_page(api_key: str, page: int) -> dict:
    resp = requests.get(
        OTX_SUBSCRIBED_URL,
        headers={"X-OTX-API-Key": api_key},
        params={"limit": PAGE_SIZE, "page": page},
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_pulses(api_key: str, context=None) -> Pull:
    pulses: list[dict] = []
    pages_fetched = 0

    for page in range(1, MAX_PAGES + 1):
        body = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if _seconds_left(context) < READ_TIMEOUT + TIME_RESERVE_SECONDS:
                return Pull(pulses, pages_fetched, f"out of time before page {page}")
            try:
                body = _get_page(api_key, page)
                break
            except Exception as exc:  # noqa: BLE001 - re-raised below unless retryable
                if not _is_transient(exc) or attempt == MAX_ATTEMPTS:
                    if not pulses:
                        raise  # nothing salvageable, so fail loudly and let the alarm fire
                    return Pull(pulses, pages_fetched, f"page {page}: {exc!r}")
                time.sleep(RETRY_BACKOFF_SECONDS)

        results = body.get("results", [])
        pulses.extend(results)
        pages_fetched += 1

        # A short page means this was the last one; `next` being null says the same thing
        # and is the documented signal, so honour whichever arrives first.
        if len(results) < PAGE_SIZE or not body.get("next"):
            break

    return Pull(pulses, pages_fetched, None)


def lambda_handler(event, context):
    api_key = os.environ["OTX_API_KEY"]
    pull = _fetch_pulses(api_key, context)

    # An empty payload is a legitimate result (an account subscribed to nothing), so it
    # gets landed - but only when the pull actually completed. Landing an empty pull that
    # merely ran out of time would overwrite a real feed with nothing AND report success,
    # which is the one failure mode the cyvora-otx-errors alarm would never catch.
    if not pull.pulses and pull.incomplete_reason:
        raise RuntimeError(f"OTX pull returned no pulses: {pull.incomplete_reason}")

    # A partial pull is still landed. The normalizer's watermark means re-seeing these
    # indicators tomorrow costs nothing, so landing 3 pages of 5 strictly beats discarding
    # all 3 - which is what raising here would do.
    key = write_raw("otx", {"pulses": pull.pulses})
    # key is None when the payload is unchanged since the last pull - see write_raw.
    return {
        "feed": "otx",
        "pulses": len(pull.pulses),
        "pages_fetched": pull.pages_fetched,
        "partial": pull.incomplete_reason is not None,
        "incomplete_reason": pull.incomplete_reason,
        "landed_key": key,
        "skipped_unchanged": key is None,
    }
