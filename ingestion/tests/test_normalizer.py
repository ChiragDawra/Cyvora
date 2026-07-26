from common.schema import IOCType
from normalizer.handler import _parse_cisa_kev, _parse_feodo, _parse_urlhaus

# Fixtures below mirror real payload shapes confirmed 2026-07-26 (see
# normalizer/handler.py's module docstring) - CISA KEV and Feodo Tracker were checked
# against live feed responses; URLhaus's field names are from abuse.ch's own docs, but
# the {"urls": [...]} wrapper is an inferred convention, not confirmed live.

CISA_KEV_RAW = {
    "title": "CISA Catalog of Known Exploited Vulnerabilities",
    "catalogVersion": "2026.07.22",
    "dateReleased": "2026-07-22T00:00:00.0000Z",
    "count": 1,
    "vulnerabilities": [
        {
            "cveID": "CVE-2026-16232",
            "vendorProject": "Check Point",
            "product": "SmartConsole",
            "vulnerabilityName": "Check Point SmartConsole Improper Authentication Vulnerability",
            "dateAdded": "2026-07-22",
            "shortDescription": "Check Point SmartConsole contains an improper authentication vulnerability.",
            "requiredAction": "Apply mitigations in accordance with vendor instructions.",
            "dueDate": "2026-07-25",
            "knownRansomwareCampaignUse": "Unknown",
            "notes": "https://support.checkpoint.com/results/sk/sk185169/",
            "cwes": ["CWE-287"],
        }
    ],
}

FEODO_RAW = [
    {
        "ip_address": "162.243.103.246",
        "port": 8080,
        "status": "offline",
        "hostname": None,
        "as_number": 14061,
        "as_name": "DIGITALOCEAN-ASN",
        "country": "US",
        "first_seen": "2022-06-04 21:24:53",
        "last_online": "2026-03-07",
        "malware": "Emotet",
    }
]

URLHAUS_RAW = {
    "query_status": "ok",
    "urls": [
        {
            "id": "12345",
            "url": "http://example.com/malware.exe",
            "url_status": "online",
            "date_added": "2026-07-20 10:00:00",
            "last_online": "2026-07-22",
            "threat": "malware_download",
            "tags": ["exe", "Emotet"],
        }
    ],
}


def test_parse_cisa_kev():
    iocs = _parse_cisa_kev(CISA_KEV_RAW)
    assert len(iocs) == 1
    ioc = iocs[0]
    assert ioc.ioc_type == IOCType.CVE
    assert ioc.value == "CVE-2026-16232"
    assert ioc.first_seen == "2026-07-22"
    assert ioc.tags == ["Check Point SmartConsole Improper Authentication Vulnerability"]


def test_parse_feodo_uses_last_online_not_last_seen():
    iocs = _parse_feodo(FEODO_RAW)
    assert len(iocs) == 1
    ioc = iocs[0]
    assert ioc.ioc_type == IOCType.IP
    assert ioc.value == "162.243.103.246"
    assert ioc.first_seen == "2022-06-04 21:24:53"
    assert ioc.last_seen == "2026-03-07"  # from last_online, not the nonexistent last_seen field
    assert ioc.tags == ["Emotet"]


def test_parse_urlhaus():
    iocs = _parse_urlhaus(URLHAUS_RAW)
    assert len(iocs) == 1
    ioc = iocs[0]
    assert ioc.ioc_type == IOCType.URL
    assert ioc.value == "http://example.com/malware.exe"
    assert ioc.first_seen == "2026-07-20 10:00:00"
    assert ioc.last_seen == "2026-07-22"
    assert ioc.tags == ["exe", "Emotet"]


def test_parse_urlhaus_falls_back_to_date_added_when_last_online_missing():
    raw = {"urls": [{"url": "http://x.test/a", "date_added": "2026-01-01", "tags": []}]}
    ioc = _parse_urlhaus(raw)[0]
    assert ioc.last_seen == "2026-01-01"
