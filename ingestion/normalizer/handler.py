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
"""
from __future__ import annotations

import json
import os
import urllib.parse

import boto3

from common.schema import IOC, IOCType

_s3 = boto3.client("s3")
_dynamodb = boto3.resource("dynamodb")


def _parse_urlhaus(raw: dict) -> list[IOC]:
    iocs = []
    for entry in raw.get("urls", []):
        iocs.append(
            IOC(
                ioc_type=IOCType.URL,
                value=entry["url"],
                source_feed="urlhaus",
                first_seen=entry.get("date_added", ""),
                last_seen=entry.get("date_added", ""),  # this endpoint has no last_online field
                tags=entry.get("tags", []) or [],
                raw=entry,
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


_PARSERS = {
    "urlhaus": _parse_urlhaus,
    "feodo": _parse_feodo,
    "cisa_kev": _parse_cisa_kev,
}


def lambda_handler(event, context):
    table = _dynamodb.Table(os.environ["IOC_TABLE"])
    written = 0

    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        feed_name = key.split("/")[0]

        parser = _PARSERS.get(feed_name)
        if parser is None:
            continue  # unrecognized feed prefix, skip rather than fail the whole batch

        obj = _s3.get_object(Bucket=bucket, Key=key)
        raw = json.loads(obj["Body"].read())

        with table.batch_writer() as batch:
            for ioc in parser(raw):
                batch.put_item(Item=ioc.to_dynamo_item())
                written += 1

    return {"written": written}
