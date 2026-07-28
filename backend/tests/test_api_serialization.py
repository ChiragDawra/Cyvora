"""Regression tests for the Decimal handling that made every API response a 500.

boto3's DynamoDB resource layer returns all numbers as Decimal, and json.dumps raises
TypeError on Decimal - so the handler returned 500 for every request until _json_default
was added.
"""
import json
from decimal import Decimal

from api.handler import _response


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
