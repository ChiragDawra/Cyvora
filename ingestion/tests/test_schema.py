from common.schema import IOC, IOCType


def test_ioc_id_is_stable_for_same_type_and_value():
    a = IOC(ioc_type=IOCType.IP, value="1.2.3.4", source_feed="feodo", first_seen="", last_seen="")
    b = IOC(ioc_type=IOCType.IP, value="1.2.3.4", source_feed="urlhaus", first_seen="x", last_seen="y")
    assert a.ioc_id == b.ioc_id  # id depends only on (type, value), not on other fields


def test_ioc_id_differs_by_type():
    ip = IOC(ioc_type=IOCType.IP, value="1.2.3.4", source_feed="feodo", first_seen="", last_seen="")
    domain = IOC(ioc_type=IOCType.DOMAIN, value="1.2.3.4", source_feed="feodo", first_seen="", last_seen="")
    assert ip.ioc_id != domain.ioc_id


def test_to_dynamo_item_omits_unset_optional_fields():
    ioc = IOC(
        ioc_type=IOCType.CVE,
        value="CVE-2026-16232",
        source_feed="cisa_kev",
        first_seen="2026-07-22",
        last_seen="2026-07-22",
        tags=["Check Point SmartConsole Improper Authentication Vulnerability"],
    )
    item = ioc.to_dynamo_item()
    assert item["ioc_type"] == "cve"
    assert item["value"] == "CVE-2026-16232"
    assert "confidence" not in item
    assert "geo" not in item


def test_to_dynamo_item_includes_confidence_and_geo_when_set():
    ioc = IOC(
        ioc_type=IOCType.IP,
        value="1.2.3.4",
        source_feed="feodo",
        first_seen="2026-01-01",
        last_seen="2026-01-02",
        confidence=87,
        geo={"country": "US"},
    )
    item = ioc.to_dynamo_item()
    assert item["confidence"] == 87
    assert item["geo"] == {"country": "US"}
