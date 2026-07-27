"""Approximate country-level centroids for map plotting.

Deliberately country-level, not IP-precise - matches EXECUTION_GUIDE.md's explicit
reframe away from "attacker origin attribution" (which IP geolocation cannot honestly
support) toward "geolocation of malicious infrastructure" at an aggregate level.
Covers the countries most common in abuse.ch/AbuseIPDB data; unmapped codes return None
and are simply omitted from the map rather than guessed at.
"""
from __future__ import annotations

_COUNTRY_CENTROIDS: dict[str, tuple[float, float]] = {
    "US": (37.09, -95.71), "CN": (35.86, 104.20), "RU": (61.52, 105.32),
    "DE": (51.17, 10.45), "GB": (55.38, -3.44), "FR": (46.23, 2.21),
    "NL": (52.13, 5.29), "BR": (-14.24, -51.93), "IN": (20.59, 78.96),
    "JP": (36.20, 138.25), "KR": (35.91, 127.77), "CA": (56.13, -106.35),
    "AU": (-25.27, 133.78), "UA": (48.38, 31.17), "PL": (51.92, 19.15),
    "IT": (41.87, 12.57), "ES": (40.46, -3.75), "SE": (60.13, 18.64),
    "SG": (1.35, 103.82), "HK": (22.40, 114.11), "VN": (14.06, 108.28),
    "ID": (-0.79, 113.92), "TH": (15.87, 100.99), "TR": (38.96, 35.24),
    "IR": (32.43, 53.69), "MX": (23.63, -102.55), "ZA": (-30.56, 22.94),
    "RO": (45.94, 24.97), "BG": (42.73, 25.49), "CZ": (49.82, 15.47),
    "SC": (-4.68, 55.49),  # Seychelles - common bulletproof-hosting jurisdiction
    "PA": (8.54, -80.78), "BZ": (17.19, -88.50), "VG": (18.42, -64.64),
}


def country_centroid(country_code: str | None) -> dict | None:
    if not country_code:
        return None
    hit = _COUNTRY_CENTROIDS.get(country_code.upper())
    if hit is None:
        return None
    lat, lon = hit
    return {"country": country_code.upper(), "lat": lat, "lon": lon}
