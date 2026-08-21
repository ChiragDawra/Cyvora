"""Covers lambda_handler's routing: which query runs, over which types, and what a
missing IOC returns.

The pagination and Decimal-serialization halves are in test_api_serialization.py. What
is pinned here is the dispatch around them - the ?geo= parsing in particular, since
getting it wrong doesn't error, it just quietly serves the recency-sorted query whose
newest items essentially never have geo yet, and the map renders empty.
"""
import json

import pytest

import api.handler as api_handler


class _FakeTable:
    """Records every query it receives and answers from `items_by_type`, so a test can
    assert on which types were asked for and with what index and ordering."""

    def __init__(self, items_by_type=None, item=None):
        self.items_by_type = items_by_type or {}
        self.item = item
        self.queries = []

    def query(self, **kwargs):
        self.queries.append(kwargs)
        ioc_type = kwargs["KeyConditionExpression"].get_expression()["values"][1]
        return {"Items": self.items_by_type.get(ioc_type, [])}

    def get_item(self, Key):  # noqa: N803 - boto3's own parameter name
        self.queries.append({"get_item": Key})
        return {"Item": self.item} if self.item is not None else {}

    def scan(self):
        return {"Items": []}


@pytest.fixture
def table(monkeypatch):
    """Swaps the module-level boto3 resource so every Table(...) lookup returns ours."""
    fake = _FakeTable()

    def install(t):
        monkeypatch.setattr(
            api_handler, "_dynamodb", type("D", (), {"Table": lambda self, name: t})()
        )

    fake.install = install
    install(fake)
    return fake


def _body(result):
    return json.loads(result["body"])


def test_type_filter_queries_only_that_type(table):
    table.items_by_type = {"ip": [{"ioc_id": "a"}]}

    result = api_handler.lambda_handler({"queryStringParameters": {"type": "ip"}}, None)

    assert [q["KeyConditionExpression"].get_expression()["values"][1] for q in table.queries] == ["ip"]
    assert _body(result)["items"] == [{"ioc_id": "a"}]


def test_no_type_filter_merges_every_known_type_newest_first(table):
    table.items_by_type = {
        "ip": [{"ioc_id": "old-ip", "ingested_at": 100}],
        "cve": [{"ioc_id": "new-cve", "ingested_at": 300}],
        "url": [{"ioc_id": "mid-url", "ingested_at": 200}],
    }

    result = api_handler.lambda_handler({}, None)

    assert len(table.queries) == len(api_handler._IOC_TYPES)  # one Query per type, no scan
    assert [i["ioc_id"] for i in _body(result)["items"]] == ["new-cve", "mid-url", "old-ip"]


def test_queries_run_against_the_gsi_newest_first(table):
    api_handler.lambda_handler({"queryStringParameters": {"type": "ip"}}, None)

    (query,) = table.queries
    assert query["IndexName"] == "type-time-index"  # not a table scan
    assert query["ScanIndexForward"] is False
    assert query["Limit"] == api_handler._QUERY_LIMIT


@pytest.mark.parametrize("value", ["1", "true", "True"])
def test_geo_param_switches_to_the_backward_paging_query(table, value, monkeypatch):
    called = []
    monkeypatch.setattr(api_handler, "_query_type_geo", lambda t, ioc_type: called.append(ioc_type) or [])

    api_handler.lambda_handler({"queryStringParameters": {"type": "ip", "geo": value}}, None)

    assert called == ["ip"]


@pytest.mark.parametrize("params", [{}, {"geo": "false"}, {"geo": "yes"}, {"geo": "0"}])
def test_anything_else_keeps_the_plain_recency_query(table, params, monkeypatch):
    """Only the three documented spellings opt in. Everything else - including "yes",
    which looks truthy but isn't in the list - must not silently change the query."""
    monkeypatch.setattr(api_handler, "_query_type_geo", lambda t, ioc_type: pytest.fail("geo query ran"))

    api_handler.lambda_handler({"queryStringParameters": {"type": "ip", **params}}, None)

    assert len(table.queries) == 1


def test_single_ioc_lookup_goes_straight_to_the_key(table):
    table.item = {"ioc_id": "abc", "value": "1.2.3.4"}

    result = api_handler.lambda_handler({"pathParameters": {"ioc_id": "abc"}}, None)

    assert table.queries == [{"get_item": {"ioc_id": "abc"}}]
    assert _body(result) == {"ioc_id": "abc", "value": "1.2.3.4"}


def test_missing_ioc_is_a_404_not_an_empty_200(table):
    table.item = None

    result = api_handler.lambda_handler({"pathParameters": {"ioc_id": "nope"}}, None)

    assert result["statusCode"] == 404
    assert _body(result) == {"error": "not found"}


def test_null_query_and_path_params_are_treated_as_absent(table):
    """API Gateway sends JSON null for these, not an empty object - `or {}` in the
    handler is what keeps that from being an AttributeError on every unfiltered call."""
    result = api_handler.lambda_handler({"queryStringParameters": None, "pathParameters": None}, None)

    assert result["statusCode"] == 200
    assert len(table.queries) == len(api_handler._IOC_TYPES)


def test_every_response_carries_cors_headers(table):
    """The frontend is served from CloudFront and calls API Gateway cross-origin, so a
    missing header here breaks the map in the browser while curl still looks fine."""
    result = api_handler.lambda_handler({"queryStringParameters": {"type": "ip"}}, None)

    assert result["headers"]["Access-Control-Allow-Origin"] == "*"
    assert result["headers"]["Content-Type"] == "application/json"


def test_alerts_route_tolerates_a_trailing_slash(table):
    """HTTP API passes rawPath through verbatim, so /alerts/ must not fall through to
    the IOC branch and query the wrong table."""
    api_handler.lambda_handler({"rawPath": "/alerts/"}, None)

    assert table.queries == []  # answered by the alerts scan, not an IOC query
