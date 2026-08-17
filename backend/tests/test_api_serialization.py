"""Regression tests for the Decimal handling that made every API response a 500.

boto3's DynamoDB resource layer returns all numbers as Decimal, and json.dumps raises
TypeError on Decimal - so the handler returned 500 for every request until _json_default
was added.
"""
import json
from decimal import Decimal

from api.handler import _query_type_geo, _response


class _FakeTable:
    """Scripted stand-in for a boto3 Table - each call to .query() returns the next
    page in `pages`, in order, ignoring the actual kwargs passed."""

    def __init__(self, pages):
        self._pages = list(pages)
        self.call_count = 0

    def query(self, **kwargs):
        self.call_count += 1
        return self._pages.pop(0)


def test_query_type_geo_stops_once_enough_matches_found():
    # First page: 100 geo-tagged items - already at _QUERY_LIMIT (100), so a second,
    # unnecessary page must never be requested.
    page = {"Items": [{"geo": {"lat": 1}}] * 100, "LastEvaluatedKey": {"ioc_id": "x"}}
    table = _FakeTable([page])

    items = _query_type_geo(table, "ip")

    assert len(items) == 100
    assert table.call_count == 1


def test_query_type_geo_paginates_when_a_page_is_sparse():
    # Each page returns only 40 matches (mimics enrichment lagging behind ingestion) -
    # must keep paging until _QUERY_LIMIT is reached.
    sparse_page = lambda has_more: {  # noqa: E731
        "Items": [{"geo": {"lat": 1}}] * 40,
        **({"LastEvaluatedKey": {"ioc_id": "x"}} if has_more else {}),
    }
    table = _FakeTable([sparse_page(True), sparse_page(True), sparse_page(True)])

    items = _query_type_geo(table, "ip")

    assert len(items) == 100  # capped at _QUERY_LIMIT, not 120
    assert table.call_count == 3


def test_query_type_geo_stops_at_max_pages_even_if_still_short():
    # No matches at all, every page claims there's more - must give up after
    # _GEO_MAX_PAGES rather than paging the whole table.
    empty_page = {"Items": [], "LastEvaluatedKey": {"ioc_id": "x"}}
    table = _FakeTable([empty_page] * 10)

    items = _query_type_geo(table, "cve")

    assert items == []
    assert table.call_count == 10


def test_response_serializes_decimals():
    body = {"items": [{"ingested_at": Decimal("1785221744"), "geo": {"lat": Decimal("37.09")}}]}
    parsed = json.loads(_response(200, body)["body"])

    item = parsed["items"][0]
    assert item["ingested_at"] == 1785221744
    assert isinstance(item["ingested_at"], int)  # epoch stays an int, not 1.785e9
    assert item["geo"]["lat"] == 37.09


def test_response_still_rejects_genuinely_unserializable_types():
    class Weird:
        pass

    try:
        _response(200, {"x": Weird()})
    except TypeError as exc:
        assert "Weird" in str(exc)
    else:
        raise AssertionError("expected TypeError")
