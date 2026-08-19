"""Optional: validates parsers against real, full feed downloads.

Neither snapshot is committed (both are multi-hundred-KB point-in-time dumps, not source
code). Fetch them yourself and place them at the repo root; each test skips if its file
is absent.

  curl -o known_exploited_vulnerabilities.json \
    https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json

  aws s3 cp "s3://$(cd infra && terraform output -raw landing_bucket)/otx/$(...).json" \
    otx_pulses.json   # any object under the otx/ prefix; the puller lands one per run
"""
import json
import pathlib

import pytest

from normalizer.handler import _parse_cisa_kev, _parse_otx

REPO_ROOT = pathlib.Path(__file__).parents[2]
REAL_KEV_PATH = REPO_ROOT / "known_exploited_vulnerabilities.json"
REAL_OTX_PATH = REPO_ROOT / "otx_pulses.json"


@pytest.mark.skipif(not REAL_KEV_PATH.exists(), reason="real KEV catalog not downloaded locally")
def test_parse_cisa_kev_against_real_full_catalog():
    raw = json.loads(REAL_KEV_PATH.read_text())
    iocs = _parse_cisa_kev(raw)

    assert len(iocs) == raw["count"]
    assert all(ioc.value and ioc.first_seen for ioc in iocs)
    assert len({ioc.value for ioc in iocs}) == len(iocs)  # every cveID is unique


@pytest.mark.skipif(not REAL_OTX_PATH.exists(), reason="no real OTX pull downloaded locally")
def test_parse_otx_against_a_real_landed_pull():
    """Pins the schema confirmed against a live pull on 2026-08-19: 100 pulses,
    2,816 indicators, of which exactly one (a YARA rule) has no honest IOCType."""
    raw = json.loads(REAL_OTX_PATH.read_text())
    indicators = [i for p in raw["pulses"] for i in (p.get("indicators") or [])]
    iocs = _parse_otx(raw)

    unmappable = [i for i in indicators if i.get("type") not in ("IPv4", "IPv6", "domain", "hostname", "URL", "URI", "FileHash-MD5", "FileHash-SHA1", "FileHash-SHA256", "CVE")]
    assert len(iocs) == len(indicators) - len(unmappable)

    assert all(ioc.value and ioc.first_seen and ioc.last_seen for ioc in iocs)
    assert all(ioc.source_feed == "otx" for ioc in iocs)

    # The same indicator legitimately appears in several pulses, so ioc_ids collide by
    # design and DynamoDB overwrites rather than duplicating. Assert the collapse is
    # real (fewer ids than IOCs) so a change that made ioc_id pulse-dependent - which
    # would silently multiply the row count - fails here.
    assert len({ioc.ioc_id for ioc in iocs}) < len(iocs)

    # first_seen feeds the watermark, which compares lexicographically, so every value
    # from this feed has to be the same zero-padded ISO shape.
    assert all(len(ioc.first_seen) >= len("2026-08-19T13:24:09") for ioc in iocs)
    assert all(ioc.first_seen[4] == "-" and ioc.first_seen[10] == "T" for ioc in iocs)
