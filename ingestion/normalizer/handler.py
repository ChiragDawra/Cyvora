"""Triggered by S3 PUT events on the landing bucket. Parses whichever feed landed the
object and writes normalized IOC records into the DynamoDB IOC table.

Field names verified against live, authenticated responses (2026-07-26/27):
- `_parse_cisa_kev`: confirmed exact against a live fetch, and re-validated against the
  full real catalog (1653 entries, zero parse failures).
- `_parse_feodo`: confirmed exact against a live, authenticated fetch of
  ipblocklist.json (top-level array; "last seen" field is `last_online`, not the
  nonexistent `last_seen`).
- `_parse_urlhaus`: confirmed exact against a live, authenticated fetch of
  /v1/urls/recent/. The `{"query_status": ..., "urls": [...]}` wrapper was correct.
  Unlike Feodo, this endpoint has NO `last_online` field at all - only `date_added` -
  so first_seen and last_seen are both set from it. `tags` can be JSON `null` (not
  just absent), handled by `entry.get("tags", []) or []`.

`_parse_otx` is the exception: it follows OTX's documented DirectConnect v1 schema but
has NOT been checked against a live authenticated payload, because no OTX key existed
when it was written. Verify it against a real landed object before relying on it.
"""
from __future__ import annotations

import ipaddress
import json
import os
import time
import urllib.parse
from collections import Counter

import boto3

from common.feed_state import get_state, put_state
from common.geo import country_centroid
from common.schema import IOC, IOCType

_s3 = boto3.client("s3")
_dynamodb = boto3.resource("dynamodb")

# How many days of daily per-type counts anomaly_detector needs to look back over.
_ANOMALY_WINDOW_DAYS = 30


def _url_host_ip(url: str) -> str | None:
    """Returns the URL's host when it's a literal IPv4 address, else None.

    A large share of URLhaus entries point straight at an IP rather than a domain. Those
    IPs are the only thing in this feed that can ever be plotted on the map - a URL has
    no location, and resolving domains to IPs is neither free nor stable. Emitting them
    as separate IP IOCs lets the AbuseIPDB enricher geo-locate them.
    """
    try:
        host = urllib.parse.urlsplit(url).hostname
    except ValueError:
        return None
    if not host:
        return None
    try:
        ipaddress.IPv4Address(host)
    except ValueError:
        return None
    return host


def _parse_urlhaus(raw: dict) -> list[IOC]:
    iocs = []
    for entry in raw.get("urls", []):
        url = entry["url"]
        date_added = entry.get("date_added", "")
        tags = entry.get("tags", []) or []

        iocs.append(
            IOC(
                ioc_type=IOCType.URL,
                value=url,
                source_feed="urlhaus",
                first_seen=date_added,
                last_seen=date_added,  # this endpoint has no last_online field
                tags=tags,
                raw=entry,
            )
        )

        host_ip = _url_host_ip(url)
        if host_ip:
            iocs.append(
                IOC(
                    ioc_type=IOCType.IP,
                    value=host_ip,
                    source_feed="urlhaus",
                    first_seen=date_added,
                    last_seen=date_added,
                    tags=tags,
                    raw={"url": url},
                )
            )
    return iocs


def _parse_feodo(raw: list[dict]) -> list[IOC]:
    iocs = []
    for entry in raw:
        iocs.append(
            IOC(
                ioc_type=IOCType.IP,
                value=entry["ip_address"],
                source_feed="feodo",
                first_seen=entry.get("first_seen", ""),
                last_seen=entry.get("last_online", ""),
                tags=[entry["malware"]] if entry.get("malware") else [],
                geo=country_centroid(entry.get("country")),  # Feodo gives country directly, no enrichment needed
                raw=entry,
            )
        )
    return iocs


def _parse_cisa_kev(raw: dict) -> list[IOC]:
    iocs = []
    for entry in raw.get("vulnerabilities", []):
        iocs.append(
            IOC(
                ioc_type=IOCType.CVE,
                value=entry["cveID"],
                source_feed="cisa_kev",
                first_seen=entry.get("dateAdded", ""),
                last_seen=entry.get("dateAdded", ""),
                tags=[entry.get("vulnerabilityName", "")],
                raw=entry,
            )
        )
    return iocs


# OTX indicator types worth storing, mapped onto the common schema. Anything absent -
# CIDR, Mutex, YARA, FilePath, email, and the rest - is skipped rather than forced into
# an IOCType it doesn't fit. FileHash-PEHASH/IMPHASH are excluded on purpose: they
# identify a binary's structure, not the binary, so they don't mean the same thing as
# the content hashes and shouldn't share a type with them.
_OTX_TYPE_MAP = {
    "IPv4": IOCType.IP,
    "IPv6": IOCType.IP,
    "domain": IOCType.DOMAIN,
    "hostname": IOCType.DOMAIN,
    "URL": IOCType.URL,
    "URI": IOCType.URL,
    "FileHash-MD5": IOCType.HASH,
    "FileHash-SHA1": IOCType.HASH,
    "FileHash-SHA256": IOCType.HASH,
    "CVE": IOCType.CVE,
}


def _parse_otx(raw: dict) -> list[IOC]:
    """Flattens subscribed pulses into per-indicator IOCs.

    OTX nests indicators inside pulses, so the same indicator can appear in several
    pulses. That collapses naturally: ioc_id is a hash of type+value, so duplicates
    overwrite rather than multiply (the same reason the batch writer sets
    overwrite_by_pkeys). Which pulse won is recorded in `raw` for traceability.

    Indicator timestamps are per-indicator (`created`) while the pulse's `modified` is
    the freshest thing known about it, so those become first_seen and last_seen. Both
    are ISO 8601 and zero-padded, which is what the watermark comparison requires.
    """
    iocs = []
    for pulse in raw.get("pulses", []):
        pulse_tags = pulse.get("tags", []) or []
        pulse_modified = pulse.get("modified", "")

        for indicator in pulse.get("indicators", []) or []:
            ioc_type = _OTX_TYPE_MAP.get(indicator.get("type"))
            if ioc_type is None:
                continue
            value = indicator.get("indicator")
            if not value:
                continue

            created = indicator.get("created", "")
            iocs.append(
                IOC(
                    ioc_type=ioc_type,
                    value=value,
                    source_feed="otx",
                    first_seen=created,
                    last_seen=pulse_modified or created,
                    tags=pulse_tags,
                    raw={"pulse_id": pulse.get("id"), "pulse_name": pulse.get("name"), **indicator},
                )
            )
    return iocs


_PARSERS = {
    "urlhaus": _parse_urlhaus,
    "feodo": _parse_feodo,
    "cisa_kev": _parse_cisa_kev,
    "otx": _parse_otx,
}


def _new_since_watermark(feed_name: str, iocs: list[IOC]) -> tuple[list[IOC], str | None]:
    """Filters out records already written on a previous run, and returns the new watermark.

    Every feed here is a rolling snapshot, not a delta: URLhaus's /urls/recent/ returns
    the same ~550 URLs on every poll, and the CISA KEV catalog re-serves all ~1,650
    entries daily. Writing all of them every time is the single biggest cost driver in
    the pipeline - hourly URLhaus polls alone would be ~4.8M DynamoDB writes/month.

    So each feed keeps a watermark: the highest source timestamp already written. Only
    strictly-newer records get written. Comparison is lexicographic, which is safe
    because a given feed always formats its timestamps identically and zero-padded
    ("2026-07-28 10:00:00 UTC", "2026-07-28"). Watermarks are never compared across feeds.
    """
    state = get_state(f"{feed_name}.watermark") or {}
    watermark = state.get("watermark")

    fresh = [ioc for ioc in iocs if not watermark or ioc.first_seen > watermark]
    timestamps = [ioc.first_seen for ioc in iocs if ioc.first_seen]
    new_watermark = max(timestamps) if timestamps else watermark

    return fresh, new_watermark


def _record_daily_counts(counts_by_type: Counter[str]) -> None:
    """Appends today's per-ioc_type write count to a rolling window in S3.

    anomaly_detector/handler.py reads this to spot per-category ingestion spikes,
    without ever touching the already-maxed-out DynamoDB provisioned capacity (see
    infra/dynamodb.tf - 24/25 WCU, 25/25 RCU account-wide, no headroom for a new read
    pattern against the main table). Written here, as a byproduct of a write the
    normalizer is already doing, rather than queried after the fact.
    """
    if not counts_by_type:
        return

    now = time.time()
    today = time.strftime("%Y-%m-%d", time.gmtime(now))
    cutoff = time.strftime("%Y-%m-%d", time.gmtime(now - _ANOMALY_WINDOW_DAYS * 86400))
    state = get_state("anomaly_counts") or {}

    for ioc_type, count in counts_by_type.items():
        series = state.setdefault(ioc_type, {})
        series[today] = series.get(today, 0) + count
        # Trim to the trailing window so this object never grows unbounded.
        for date in [d for d in series if d < cutoff]:
            del series[date]

    put_state("anomaly_counts", state)


def lambda_handler(event, context):
    table = _dynamodb.Table(os.environ["IOC_TABLE"])
    written = 0
    skipped = 0
    written_by_type: Counter[str] = Counter()

    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        feed_name = key.split("/")[0]

        parser = _PARSERS.get(feed_name)
        if parser is None:
            continue  # unrecognized feed prefix (e.g. _state/), skip rather than fail the batch

        obj = _s3.get_object(Bucket=bucket, Key=key)
        raw = json.loads(obj["Body"].read())

        parsed = parser(raw)
        fresh, new_watermark = _new_since_watermark(feed_name, parsed)
        skipped += len(parsed) - len(fresh)

        # overwrite_by_pkeys: one URLhaus pull can yield several URLs on the same host IP,
        # and BatchWriteItem rejects a request containing duplicate keys.
        with table.batch_writer(overwrite_by_pkeys=["ioc_id"]) as batch:
            for ioc in fresh:
                batch.put_item(Item=ioc.to_dynamo_item())
                written += 1
                written_by_type[ioc.ioc_type.value] += 1

        # Only advance the watermark after the writes land - a mid-batch failure re-runs
        # the whole object rather than silently dropping records.
        if new_watermark:
            put_state(feed_name + ".watermark", {"watermark": new_watermark})

    _record_daily_counts(written_by_type)

    return {"written": written, "skipped_already_seen": skipped}
