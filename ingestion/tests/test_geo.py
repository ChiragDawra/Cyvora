from common.geo import country_centroid


def test_known_country_returns_centroid():
    result = country_centroid("US")
    assert result == {"country": "US", "lat": 37.09, "lon": -95.71}


def test_lowercase_country_code_normalized():
    assert country_centroid("us") == country_centroid("US")


def test_unknown_country_returns_none():
    assert country_centroid("ZZ") is None


def test_none_or_empty_returns_none():
    assert country_centroid(None) is None
    assert country_centroid("") is None
