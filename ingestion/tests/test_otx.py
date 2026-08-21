"""Covers the OTX puller's pagination and the normalizer's pulse-flattening parser.

The payload fixtures follow OTX's documented DirectConnect v1 schema. Unlike the other
three feeds they are NOT transcribed from a live authenticated response - see
normalizer/handler.py's docstring - so these tests pin the mapping logic, not the
upstream field names.
"""
from collections import Counter

import pytest
import requests

import otx.handler as otx_handler
from common.schema import IOCType
from normalizer.handler import _parse_otx

OTX_RAW = {
    "pulses": [
        {
            "id": "6650f0d1a1b2c3d4e5f60001",
            "name": "Emotet distribution infrastructure",
            "modified": "2026-08-16T09:12:44",
            "tags": ["emotet", "banker"],
            "indicators": [
                {"id": 1, "indicator": "45.132.192.10", "type": "IPv4", "created": "2026-08-15T11:00:00"},
                {"id": 2, "indicator": "2a02:4780:1:1::5", "type": "IPv6", "created": "2026-08-15T11:00:01"},
                {"id": 3, "indicator": "bad-update.example", "type": "domain", "created": "2026-08-15T11:00:02"},
                {"id": 4, "indicator": "cdn.bad-update.example", "type": "hostname", "created": "2026-08-15T11:00:03"},
                {"id": 5, "indicator": "http://bad-update.example/x.bin", "type": "URL", "created": "2026-08-15T11:00:04"},
                {"id": 6, "indicator": "d41d8cd98f00b204e9800998ecf8427e", "type": "FileHash-MD5", "created": "2026-08-15T11:00:05"},
                {"id": 7, "indicator": "CVE-2026-16232", "type": "CVE", "created": "2026-08-15T11:00:06"},
                # Skipped: no IOCType these honestly map onto.
                {"id": 8, "indicator": "45.132.192.0/24", "type": "CIDR", "created": "2026-08-15T11:00:07"},
                {"id": 9, "indicator": "Global\\MutexName", "type": "Mutex", "created": "2026-08-15T11:00:08"},
                {"id": 10, "indicator": "0x1a2b3c4d", "type": "FileHash-IMPHASH", "created": "2026-08-15T11:00:09"},
            ],
        }
    ]
}


def _by_value(iocs):
    return {ioc.value: ioc for ioc in iocs}


def test_parse_otx_maps_every_supported_indicator_type():
    iocs = _parse_otx(OTX_RAW)

    assert len(iocs) == 7  # 10 indicators, 3 unmappable types dropped
    types = Counter(ioc.ioc_type for ioc in iocs)
    assert types == {
        IOCType.IP: 2,  # IPv4 + IPv6
        IOCType.DOMAIN: 2,  # domain + hostname
        IOCType.URL: 1,
        IOCType.HASH: 1,
        IOCType.CVE: 1,
    }


def test_parse_otx_drops_indicator_types_with_no_honest_mapping():
    values = _by_value(_parse_otx(OTX_RAW))

    assert "45.132.192.0/24" not in values  # CIDR is a range, not an IOC value
    assert "Global\\MutexName" not in values
    assert "0x1a2b3c4d" not in values  # IMPHASH describes structure, not content


def test_parse_otx_takes_first_seen_from_indicator_and_last_seen_from_pulse():
    ioc = _by_value(_parse_otx(OTX_RAW))["45.132.192.10"]

    assert ioc.first_seen == "2026-08-15T11:00:00"
    assert ioc.last_seen == "2026-08-16T09:12:44"  # the pulse's modified time
    assert ioc.source_feed == "otx"


def test_parse_otx_falls_back_to_indicator_created_when_pulse_has_no_modified():
    raw = {"pulses": [{"id": "p", "indicators": [{"indicator": "1.2.3.4", "type": "IPv4", "created": "2026-08-15T11:00:00"}]}]}

    (ioc,) = _parse_otx(raw)

    assert ioc.last_seen == "2026-08-15T11:00:00"


def test_parse_otx_inherits_pulse_tags_and_records_pulse_provenance():
    ioc = _by_value(_parse_otx(OTX_RAW))["bad-update.example"]

    assert ioc.tags == ["emotet", "banker"]
    assert ioc.raw["pulse_id"] == "6650f0d1a1b2c3d4e5f60001"
    assert ioc.raw["pulse_name"] == "Emotet distribution infrastructure"


def test_parse_otx_tolerates_null_tags_and_null_indicators():
    """OTX sends JSON null rather than omitting these, same as URLhaus does for tags."""
    raw = {"pulses": [{"id": "a", "tags": None, "indicators": None}, {"id": "b", "tags": None, "indicators": [
        {"indicator": "9.9.9.9", "type": "IPv4", "created": "2026-08-15T11:00:00"}
    ]}]}

    (ioc,) = _parse_otx(raw)

    assert ioc.tags == []


def test_parse_otx_skips_indicators_with_no_value():
    raw = {"pulses": [{"id": "a", "indicators": [{"indicator": "", "type": "IPv4", "created": "x"}]}]}

    assert _parse_otx(raw) == []


def test_parse_otx_on_empty_subscription_returns_nothing():
    """A fresh OTX account subscribed to no pulses - a no-op, not an error."""
    assert _parse_otx({"pulses": []}) == []


class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def _page(count, has_next=True):
    results = [{"id": f"p{i}", "indicators": []} for i in range(count)]
    return {"results": results, "next": "http://next" if has_next else None}


def _http_error(status):
    """A requests.HTTPError carrying a response, the way raise_for_status raises it -
    _is_transient reads .response.status_code off it."""
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"{status}", response=response)


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch):
    """Retries back off for RETRY_BACKOFF_SECONDS; nothing here should actually wait."""
    monkeypatch.setattr(otx_handler.time, "sleep", lambda seconds: None)


class _Clock:
    """Stands in for the Lambda context object, whose get_remaining_time_in_millis is the
    only signal the handler has that it is about to be killed mid-request."""

    def __init__(self, seconds_left):
        self.seconds_left = seconds_left

    def get_remaining_time_in_millis(self):
        return self.seconds_left * 1000


def test_fetch_pulses_follows_pages_until_a_short_one(monkeypatch):
    pages = [_page(otx_handler.PAGE_SIZE), _page(otx_handler.PAGE_SIZE), _page(3)]
    seen = []

    def fake_get(url, headers, params, timeout):
        seen.append(params["page"])
        return _FakeResponse(pages[params["page"] - 1])

    monkeypatch.setattr(otx_handler.requests, "get", fake_get)

    pull = otx_handler._fetch_pulses("key")

    assert seen == [1, 2, 3]
    assert len(pull.pulses) == otx_handler.PAGE_SIZE * 2 + 3
    assert pull.pages_fetched == 3
    assert pull.incomplete_reason is None


def test_fetch_pulses_stops_when_next_is_null_even_on_a_full_page(monkeypatch):
    def fake_get(url, headers, params, timeout):
        return _FakeResponse(_page(otx_handler.PAGE_SIZE, has_next=False))

    monkeypatch.setattr(otx_handler.requests, "get", fake_get)

    assert len(otx_handler._fetch_pulses("key").pulses) == otx_handler.PAGE_SIZE


def test_fetch_pulses_never_exceeds_the_page_cap(monkeypatch):
    """Pulses carry indicators inline, so an uncapped loop could land a huge object."""
    calls = []

    def fake_get(url, headers, params, timeout):
        calls.append(params["page"])
        return _FakeResponse(_page(otx_handler.PAGE_SIZE))

    monkeypatch.setattr(otx_handler.requests, "get", fake_get)

    pull = otx_handler._fetch_pulses("key")

    assert len(calls) == otx_handler.MAX_PAGES
    assert len(pull.pulses) == otx_handler.PAGE_SIZE * otx_handler.MAX_PAGES


def test_fetch_pulses_sends_the_api_key_header(monkeypatch):
    captured = {}

    def fake_get(url, headers, params, timeout):
        captured.update(url=url, headers=headers, timeout=timeout)
        return _FakeResponse(_page(0, has_next=False))

    monkeypatch.setattr(otx_handler.requests, "get", fake_get)
    otx_handler._fetch_pulses("secret-key")

    assert captured["url"] == otx_handler.OTX_SUBSCRIBED_URL
    assert captured["headers"] == {"X-OTX-API-Key": "secret-key"}
    # Split connect/read, not one scalar - a dead socket and a slow cache warrant
    # very different patience. See the handler's timeout constants.
    assert captured["timeout"] == (otx_handler.CONNECT_TIMEOUT, otx_handler.READ_TIMEOUT)


def test_fetch_pulses_retries_a_read_timeout_and_succeeds(monkeypatch):
    """The 2026-08-21 production failure: OTX's cache is cold, the first read times out
    at ~34s, and that very request warms it so the retry returns in under 3s."""
    attempts = []

    def fake_get(url, headers, params, timeout):
        attempts.append(params["page"])
        if len(attempts) == 1:
            raise requests.Timeout("read timed out")
        return _FakeResponse(_page(2, has_next=False))

    monkeypatch.setattr(otx_handler.requests, "get", fake_get)

    pull = otx_handler._fetch_pulses("key")

    assert attempts == [1, 1]  # same page, twice
    assert len(pull.pulses) == 2
    assert pull.incomplete_reason is None  # a retried success is a clean pull


def test_fetch_pulses_retries_a_429_and_a_500_but_not_a_401(monkeypatch):
    """A rate-limit or server fault may pass; a rejected API key will be just as rejected
    a second later, so retrying it only burns the Lambda's time budget."""
    for status, expected_attempts in [(429, 2), (503, 2), (401, 1)]:
        attempts = []

        def fake_get(url, headers, params, timeout, status=status):
            attempts.append(1)
            raise _http_error(status)

        monkeypatch.setattr(otx_handler.requests, "get", fake_get)

        with pytest.raises(requests.HTTPError):
            otx_handler._fetch_pulses("key")

        assert len(attempts) == expected_attempts, f"status {status}"


def test_fetch_pulses_raises_when_the_very_first_page_never_arrives(monkeypatch):
    """Nothing salvageable, so this must stay a hard failure - it is what makes the
    cyvora-otx-errors alarm fire."""

    def fake_get(url, headers, params, timeout):
        raise requests.Timeout("read timed out")

    monkeypatch.setattr(otx_handler.requests, "get", fake_get)

    with pytest.raises(requests.Timeout):
        otx_handler._fetch_pulses("key")


def test_fetch_pulses_returns_what_it_has_when_a_later_page_fails(monkeypatch):
    """Two good pages beat discarding both. The normalizer's watermark makes re-seeing
    these indicators on the next run free, so a partial pull loses nothing."""

    def fake_get(url, headers, params, timeout):
        if params["page"] >= 3:
            raise requests.ConnectionError("reset by peer")
        return _FakeResponse(_page(otx_handler.PAGE_SIZE))

    monkeypatch.setattr(otx_handler.requests, "get", fake_get)

    pull = otx_handler._fetch_pulses("key")

    assert pull.pages_fetched == 2
    assert len(pull.pulses) == otx_handler.PAGE_SIZE * 2
    assert "page 3" in pull.incomplete_reason


def test_fetch_pulses_stops_paging_before_lambda_would_kill_it(monkeypatch):
    """Being killed mid-request loses every page already fetched and logs no traceback,
    which is strictly worse than stopping early and landing what we have."""
    clock = _Clock(seconds_left=otx_handler.READ_TIMEOUT + otx_handler.TIME_RESERVE_SECONDS + 1)

    def fake_get(url, headers, params, timeout):
        clock.seconds_left -= 30  # each page eats into the deadline
        return _FakeResponse(_page(otx_handler.PAGE_SIZE))

    monkeypatch.setattr(otx_handler.requests, "get", fake_get)

    pull = otx_handler._fetch_pulses("key", clock)

    assert pull.pages_fetched == 1  # not MAX_PAGES
    assert pull.incomplete_reason == "out of time before page 2"


def test_fetch_pulses_ignores_the_clock_outside_lambda(monkeypatch):
    """Local runs and tests pass no context; there is no deadline to respect."""

    def fake_get(url, headers, params, timeout):
        return _FakeResponse(_page(1, has_next=False))

    monkeypatch.setattr(otx_handler.requests, "get", fake_get)

    assert otx_handler._fetch_pulses("key", None).incomplete_reason is None


def test_lambda_handler_wraps_pulses_and_reports_the_landed_key(monkeypatch):
    landed = {}

    monkeypatch.setattr(
        otx_handler, "_fetch_pulses", lambda key, context: otx_handler.Pull([{"id": "p1"}], 1, None)
    )
    monkeypatch.setattr(
        otx_handler, "write_raw", lambda feed, payload: landed.update(feed=feed, payload=payload) or "otx/123.json"
    )
    monkeypatch.setenv("OTX_API_KEY", "k")

    result = otx_handler.lambda_handler({}, None)

    assert landed["feed"] == "otx"
    assert landed["payload"] == {"pulses": [{"id": "p1"}]}
    assert result == {
        "feed": "otx",
        "pulses": 1,
        "pages_fetched": 1,
        "partial": False,
        "incomplete_reason": None,
        "landed_key": "otx/123.json",
        "skipped_unchanged": False,
    }


def test_lambda_handler_lands_a_partial_pull_and_says_so(monkeypatch):
    landed = {}

    monkeypatch.setattr(
        otx_handler,
        "_fetch_pulses",
        lambda key, context: otx_handler.Pull([{"id": "p1"}], 2, "page 3: Timeout()"),
    )
    monkeypatch.setattr(otx_handler, "write_raw", lambda feed, payload: landed.update(payload=payload) or "otx/1.json")
    monkeypatch.setenv("OTX_API_KEY", "k")

    result = otx_handler.lambda_handler({}, None)

    assert landed["payload"] == {"pulses": [{"id": "p1"}]}  # landed, not discarded
    assert result["partial"] is True
    assert result["incomplete_reason"] == "page 3: Timeout()"


def test_lambda_handler_lands_a_genuinely_empty_subscription(monkeypatch):
    """An account subscribed to no pulses is a no-op, not an error."""
    monkeypatch.setattr(otx_handler, "_fetch_pulses", lambda key, context: otx_handler.Pull([], 1, None))
    monkeypatch.setattr(otx_handler, "write_raw", lambda feed, payload: "otx/1.json")
    monkeypatch.setenv("OTX_API_KEY", "k")

    assert otx_handler.lambda_handler({}, None)["pulses"] == 0


def test_lambda_handler_refuses_to_land_an_empty_pull_that_ran_out_of_time(monkeypatch):
    """Otherwise a timed-out run overwrites a real feed with nothing and reports success -
    the one failure mode the error alarm would never catch."""
    monkeypatch.setattr(
        otx_handler, "_fetch_pulses", lambda key, context: otx_handler.Pull([], 0, "out of time before page 1")
    )
    monkeypatch.setattr(
        otx_handler, "write_raw", lambda feed, payload: pytest.fail("must not land an empty timed-out pull")
    )
    monkeypatch.setenv("OTX_API_KEY", "k")

    with pytest.raises(RuntimeError, match="out of time"):
        otx_handler.lambda_handler({}, None)


def test_lambda_handler_reports_an_unchanged_payload_as_skipped(monkeypatch):
    monkeypatch.setattr(otx_handler, "_fetch_pulses", lambda key, context: otx_handler.Pull([{"id": "p"}], 1, None))
    monkeypatch.setattr(otx_handler, "write_raw", lambda feed, payload: None)
    monkeypatch.setenv("OTX_API_KEY", "k")

    assert otx_handler.lambda_handler({}, None)["skipped_unchanged"] is True


def test_lambda_handler_fails_loudly_without_an_api_key(monkeypatch):
    monkeypatch.delenv("OTX_API_KEY", raising=False)

    with pytest.raises(KeyError):
        otx_handler.lambda_handler({}, None)
