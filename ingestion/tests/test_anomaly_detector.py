import anomaly_detector.handler as h


def _baseline(count, days=10):
    """A flat (zero-variance) baseline series for the trailing `days` days ending
    yesterday. Only useful for tests that specifically want stdev == 0."""
    import time

    series = {}
    for i in range(1, days + 1):
        date = time.strftime("%Y-%m-%d", time.gmtime(time.time() - i * 86400))
        series[date] = count
    return series


def _varied_baseline():
    """A baseline with real variance, so a genuine spike produces a finite z-score
    instead of hitting the zero-stdev guard."""
    import time

    series = {}
    for i, count in enumerate([10, 12, 9, 11, 10, 13, 9, 10, 11, 12], start=1):
        date = time.strftime("%Y-%m-%d", time.gmtime(time.time() - i * 86400))
        series[date] = count
    return series


def _today():
    import time

    return time.strftime("%Y-%m-%d", time.gmtime())


def test_detect_anomalies_flags_clear_spike():
    series = _varied_baseline()
    series[_today()] = 100  # a huge jump against a mean of ~10.7

    anomalies = h._detect_anomalies({"ip": series})

    assert len(anomalies) == 1
    assert anomalies[0]["ioc_type"] == "ip"
    assert anomalies[0]["count"] == 100


def test_detect_anomalies_ignores_normal_variation():
    import time

    series = {}
    for i, count in enumerate([10, 12, 9, 11, 10, 13, 9, 10], start=1):
        date = time.strftime("%Y-%m-%d", time.gmtime(time.time() - i * 86400))
        series[date] = count
    series[_today()] = 11  # well within normal range

    assert h._detect_anomalies({"ip": series}) == []


def test_detect_anomalies_requires_minimum_baseline_history():
    series = _baseline(3)  # fewer than _MIN_BASELINE_DAYS
    series[_today()] = 1000

    assert h._detect_anomalies({"ip": series}) == []


def test_detect_anomalies_zero_stdev_baseline_never_flags():
    """A perfectly flat baseline (stdev 0) has nothing to compare against - must not
    divide by zero or flag every non-identical day."""
    series = _baseline(10)
    series[_today()] = 11  # any deviation from a constant baseline

    assert h._detect_anomalies({"ip": series}) == []


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


def test_lambda_handler_publishes_and_records_each_anomaly(monkeypatch):
    series = _varied_baseline()
    series[_today()] = 500
    monkeypatch.setattr(h, "get_state", lambda name: {"ip": series})

    fake_table = _FakeTable()
    fake_sns = _FakeSns()
    monkeypatch.setattr(h, "_dynamodb", type("D", (), {"Table": lambda self, name: fake_table})())
    monkeypatch.setattr(h, "_sns", fake_sns)
    monkeypatch.setenv("ALERTS_TABLE", "cyvora-alerts-test")
    monkeypatch.setenv("ALERTS_TOPIC_ARN", "arn:aws:sns:us-east-1:123:cyvora-alerts")

    result = h.lambda_handler({}, None)

    assert result == {"anomalies_flagged": 1}
    assert len(fake_table.items) == 1
    assert fake_table.items[0]["ioc_type"] == "ip"
    assert "alert_id" in fake_table.items[0]
    assert len(fake_sns.published) == 1
    assert fake_sns.published[0]["TopicArn"] == "arn:aws:sns:us-east-1:123:cyvora-alerts"


def test_lambda_handler_noop_when_nothing_anomalous(monkeypatch):
    monkeypatch.setattr(h, "get_state", lambda name: {"ip": _baseline(10)})
    result = h.lambda_handler({}, None)
    assert result == {"anomalies_flagged": 0}
