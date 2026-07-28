"""Common IOC schema that every feed's raw output gets normalized into.

Kept intentionally small for v1 — extend fields only when a real feed/consumer needs them.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum


# How long an IOC stays in DynamoDB before TTL removes it. 90 days is well past the
# useful life of a URLhaus/Feodo entry and keeps the table comfortably inside the
# always-free 25 GB.
TTL_SECONDS = 90 * 24 * 60 * 60


class IOCType(str, Enum):
    IP = "ip"
    DOMAIN = "domain"
    URL = "url"
    HASH = "hash"
    CVE = "cve"


@dataclass
class IOC:
    ioc_type: IOCType
    value: str
    source_feed: str
    first_seen: str  # ISO 8601
    last_seen: str  # ISO 8601
    tags: list[str] = field(default_factory=list)
    confidence: int | None = None  # 0-100, only set when a feed provides it
    geo: dict | None = None  # {"lat": float, "lon": float, "country": str} - set by enrichment, not ingestion
    raw: dict = field(default_factory=dict)  # original record, kept for traceability/debugging

    @property
    def ioc_id(self) -> str:
        digest = hashlib.sha256(f"{self.ioc_type.value}:{self.value}".encode()).hexdigest()
        return digest[:32]

    def to_dynamo_item(self) -> dict:
        now = int(time.time())
        item = {
            "ioc_id": self.ioc_id,
            "ioc_type": self.ioc_type.value,
            "value": self.value,
            "source_feed": self.source_feed,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "tags": self.tags,
            "ingested_at": now,
            # Consumed by the TTL config in infra/dynamodb.tf. Threat intel goes stale
            # fast and this is the only thing keeping the table inside DynamoDB's
            # always-free 25 GB. TTL deletes cost no write capacity.
            "expires_at": now + TTL_SECONDS,
        }
        if self.confidence is not None:
            item["confidence"] = self.confidence
        if self.geo is not None:
            item["geo"] = self.geo
        return item
