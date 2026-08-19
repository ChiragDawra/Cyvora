import time

import anomaly_detector.handler as h

# A fixed UTC instant, so every date in this module is derived from one clock reading.
# Previously each helper called time.time() separately and compared against the handler's
# own reading, which meant a run straddling UTC midnight would build its baseline for one
# day and assert against another.
NOW = 1786800000.0  # 2026-08-15T00:00:00Z
TODAY = "2026-08-15"


def _days_before(offset: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(NOW - offset * 86400))


def _series(counts: list[int]) -> dict[str, int]:
    """Builds a series over the days immediately preceding TODAY, newest first."""
    return {_days_before(i): count for i, count in enumerate(counts, start=1)}


def _flat_baseline(count: int, days: int = 10) -> dict[str, int]:
    """A zero-variance baseline. Only for tests that specifically want stdev == 0."""
    return _series([count] * days)


def _varied_baseline() -> dict[str, int]:
    """A baseline with real variance, so a genuine spike produces a finite z-score
    instead of hitting the zero-stdev guard."""
    return _series([10, 12, 9, 11, 10, 13, 9, 10, 11, 12])


def test_detect_anomalies_flags_clear_spike():
    series = _varied_baseline()
    series[TODAY] = 100  # a huge jump against a mean of ~10.7

    anomalies = h._detect_anomalies({"ip": series}, now=NOW)

    assert len(anomalies) == 1
    assert anomalies[0]["ioc_type"] == "ip"
    assert anomalies[0]["count"] == 100
    assert anomalies[0]["date"] == TODAY
    assert anomalies[0]["z_score"] > 3


def test_detect_anomalies_ignores_normal_variation():
    series = _series([10, 12, 9, 11, 10, 13, 9, 10])
    series[TODAY] = 11  # well within normal range

    assert h._detect_anomalies({"ip": series}, now=NOW) == []


def test_detect_anomalies_requires_minimum_baseline_history():
    series = _flat_baseline(3, days=h._MIN_BASELINE_DAYS - 1)
    series[TODAY] = 1000

    assert h._detect_anomalies({"ip": series}, now=NOW) == []


def test_detect_anomalies_zero_stdev_baseline_never_flags():
    """A perfectly flat baseline (stdev 0) has nothing to compare against - must not
    divide by zero or flag every non-identical day."""
    series = _flat_baseline(10)
    series[TODAY] = 11  # any deviation from a constant baseline

    assert h._detect_anomalies({"ip": series}, now=NOW) == []


def test_detect_anomalies_ignores_a_drop():
    """The rule is one-sided on purpose: a feed going quiet is usually an outage
    upstream, and the error alarms already cover that. Only spikes alert."""
    series = _varied_baseline()
    series[TODAY] = 0

    assert h._detect_anomalies({"ip": series}, now=NOW) == []


def test_detect_anomalies_treats_a_missing_today_as_zero_not_as_absent():
    """A type that ingested nothing today has no key in the series at all."""
    assert h._detect_anomalies({"ip": _varied_baseline()}, now=NOW) == []


def test_detect_anomalies_judges_each_type_independently():
    spiking = _varied_baseline()
    spiking[TODAY] = 100
    calm = _varied_baseline()
    calm[TODAY] = 11

    anomalies = h._detect_anomalies({"ip": spiking, "url": calm}, now=NOW)

    assert [a["ioc_type"] for a in anomalies] == ["ip"]


def test_detect_anomalies_on_empty_state_returns_nothing():
    assert h._detect_anomalies({}, now=NOW) == []


class _FakeTable:
    def __init__(self):
        self.items = []

    def put_item(self, Item):
        self.items.append(Item)


class _FakeSns:
    def __init__(self):
        self.published = []

    def publish(self, **kwargs):
        self.published.append(kwargs)


def _wire_aws(monkeypatch):
    fake_table = _FakeTable()
    fake_sns = _FakeSns()
    monkeypatch.setattr(h, "_dynamodb", type("D", (), {"Table": lambda self, name: fake_table})())
    monkeypatch.setattr(h, "_sns", fake_sns)
    monkeypatch.setenv("ALERTS_TABLE", "cyvora-alerts-test")
    monkeypatch.setenv("ALERTS_TOPIC_ARN", "arn:aws:sns:us-east-1:123:cyvora-alerts")
    return fake_table, fake_sns


def _spiking_state():
    """Built against the real current day, since lambda_handler reads the clock itself."""
    today = time.strftime("%Y-%m-%d", time.gmtime())
    series = {
        time.strftime("%Y-%m-%d", time.gmtime(time.time() - i * 86400)): count
        for i, count in enumerate([10, 12, 9, 11, 10, 13, 9, 10, 11, 12], start=1)
    }
    series[today] = 500
    return {"ip": series}


def test_lambda_handler_publishes_and_records_each_anomaly(monkeypatch):
    monkeypatch.setattr(h, "get_state", lambda name: _spiking_state())
    fake_table, fake_sns = _wire_aws(monkeypatch)

    result = h.lambda_handler({}, None)

    assert result == {"anomalies_flagged": 1}
    assert len(fake_table.items) == 1
    assert fake_table.items[0]["ioc_type"] == "ip"
    assert "alert_id" in fake_table.items[0]
    assert len(fake_sns.published) == 1
    assert fake_sns.published[0]["TopicArn"] == "arn:aws:sns:us-east-1:123:cyvora-alerts"


def test_lambda_handler_sets_a_ttl_on_every_alert(monkeypatch):
    """Without expires_at the alerts table grows forever - see infra/dynamodb.tf's ttl."""
    monkeypatch.setattr(h, "get_state", lambda name: _spiking_state())
    fake_table, _ = _wire_aws(monkeypatch)

    h.lambda_handler({}, None)
    item = fake_table.items[0]

    assert item["expires_at"] - item["created_at"] == h._ALERT_TTL_SECONDS


def test_lambda_handler_noop_when_nothing_anomalous(monkeypatch):
    monkeypatch.setattr(h, "get_state", lambda name: {"ip": _flat_baseline(10)})

    assert h.lambda_handler({}, None) == {"anomalies_flagged": 0}


def test_lambda_handler_touches_no_aws_when_there_is_nothing_to_report(monkeypatch):
    """The no-anomaly path is the every-day path, so it must not open the table or
    publish - both cost money and neither has anything to do."""
    monkeypatch.setattr(h, "get_state", lambda name: {})
    fake_table, fake_sns = _wire_aws(monkeypatch)
    monkeypatch.delenv("ALERTS_TABLE")  # a lookup would now raise rather than pass quietly

    assert h.lambda_handler({}, None) == {"anomalies_flagged": 0}
    assert fake_table.items == []
    assert fake_sns.published == []


def test_lambda_handler_handles_state_that_has_never_been_written(monkeypatch):
    """get_state returns None before the normalizer's first run - see feed_state.py."""
    monkeypatch.setattr(h, "get_state", lambda name: None)

    assert h.lambda_handler({}, None) == {"anomalies_flagged": 0}
