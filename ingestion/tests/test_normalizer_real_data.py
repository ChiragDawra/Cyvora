"""Optional: validates the CISA KEV parser against a real, full catalog download.

Not committed to the repo (it's a multi-MB point-in-time snapshot, not source code) -
download it yourself with:
  curl -o known_exploited_vulnerabilities.json \
    https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
and place it at the repo root. Skipped automatically if absent.
"""
import json
import pathlib

import pytest

from normalizer.handler import _parse_cisa_kev

REAL_KEV_PATH = pathlib.Path(__file__).parents[2] / "known_exploited_vulnerabilities.json"


@pytest.mark.skipif(not REAL_KEV_PATH.exists(), reason="real KEV catalog not downloaded locally")
def test_parse_cisa_kev_against_real_full_catalog():
    raw = json.loads(REAL_KEV_PATH.read_text())
    iocs = _parse_cisa_kev(raw)

    assert len(iocs) == raw["count"]
    assert all(ioc.value and ioc.first_seen for ioc in iocs)
    assert len({ioc.value for ioc in iocs}) == len(iocs)  # every cveID is unique
