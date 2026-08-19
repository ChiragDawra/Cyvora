"""Flags per-ioc_type ingestion spikes and publishes them as SNS alerts.

Reads the daily per-type write counts the normalizer already records in
`_state/anomaly_counts.json` (see normalizer/handler.py's _record_daily_counts) rather
than querying DynamoDB directly - the main IOC table is already at its provisioned
capacity ceiling (infra/dynamodb.tf: 24/25 WCU, 25/25 RCU account-wide), so this Lambda
must add zero read load against it.

Anomaly rule: for each ioc_type with at least MIN_BASELINE_DAYS of history (excluding
today), compute mean/stdev of the trailing window via stdlib `statistics` (no numpy -
keeps the shared Lambda layer unchanged) and flag today's count if it's more than
Z_THRESHOLD standard deviations above the mean. A zero-stdev baseline (every day
identical) never flags - there's nothing to compare against.
"""
from __future__ import annotations

import os
import statistics
import time
import uuid

import boto3

from common.feed_state import get_state

_MIN_BASELINE_DAYS = 7
_Z_THRESHOLD = 3
_ALERT_TTL_SECONDS = 30 * 24 * 60 * 60

_dynamodb = boto3.resource("dynamodb")
_sns = boto3.client("sns")


def _detect_anomalies(state: dict, now: float | None = None) -> list[dict]:
    """`now` is injectable so tests can pin the UTC day rather than racing midnight:
    a test that builds its baseline from one clock reading and asserts against another
    fails once a day, at the boundary, for no real reason."""
    today = time.strftime("%Y-%m-%d", time.gmtime(time.time() if now is None else now))
    anomalies = []

    for ioc_type, series in state.items():
        today_count = series.get(today, 0)
        baseline = [count for date, count in series.items() if date != today]

        if len(baseline) < _MIN_BASELINE_DAYS:
            continue  # not enough history to judge what's normal yet

        mean = statistics.mean(baseline)
        stdev = statistics.stdev(baseline)
        if stdev == 0:
            continue  # no variation in the baseline - nothing to compare against

        z_score = (today_count - mean) / stdev
        if z_score > _Z_THRESHOLD:
            anomalies.append(
                {
                    "ioc_type": ioc_type,
                    "date": today,
                    "count": today_count,
                    "baseline_mean": round(mean, 2),
                    "baseline_stdev": round(stdev, 2),
                    "z_score": round(z_score, 2),
                }
            )

    return anomalies


def _publish_and_record(anomaly: dict, table, topic_arn: str) -> None:
    now = int(time.time())
    item = {
        "alert_id": uuid.uuid4().hex,
        "created_at": now,
        "expires_at": now + _ALERT_TTL_SECONDS,
        **anomaly,
    }
    table.put_item(Item=item)

    _sns.publish(
        TopicArn=topic_arn,
        Subject=f"Cyvora anomaly: {anomaly['ioc_type']} volume spike",
        Message=(
            f"{anomaly['ioc_type']} IOC ingestion on {anomaly['date']}: "
            f"{anomaly['count']} (baseline mean {anomaly['baseline_mean']}, "
            f"stdev {anomaly['baseline_stdev']}, z-score {anomaly['z_score']})"
        ),
    )


def lambda_handler(event, context):
    state = get_state("anomaly_counts") or {}
    anomalies = _detect_anomalies(state)

    if anomalies:
        table = _dynamodb.Table(os.environ["ALERTS_TABLE"])
        topic_arn = os.environ["ALERTS_TOPIC_ARN"]
        for anomaly in anomalies:
            _publish_and_record(anomaly, table, topic_arn)

    return {"anomalies_flagged": len(anomalies)}
