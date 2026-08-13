"""Unit tests for OSINT source allowlist filters."""

from thot.tools.collector.quality import (
    clear_osint_sources_cache,
    filter_search_hits,
    host_matches_allowlist,
    is_allowed_osint_hit,
    parse_osint_sources,
)


def setup_function() -> None:
    clear_osint_sources_cache()


def test_parse_osint_sources():
    enabled, hosts = parse_osint_sources(
        {"enabled": True, "hosts": ["NASA.GOV", "usgs.gov"]}
    )
    assert enabled is True
    assert hosts == frozenset({"nasa.gov", "usgs.gov"})


def test_subdomain_match():
    allow = frozenset({"nasa.gov"})
    assert host_matches_allowlist("firms.modaps.eosdis.nasa.gov", allow)
    assert not host_matches_allowlist("evil.com", allow)


def test_filter_search_hits_allowlist():
    allow = frozenset({"nasa.gov", "usgs.gov"})
    kept = filter_search_hits(
        [
            {"url": "https://nasa.gov/fire", "title": "Wildfire"},
            {"url": "https://xvideos.com/a", "title": "x"},
            {"url": "https://earthquake.usgs.gov/eq", "title": "Quake"},
        ],
        enabled=True,
        allow=allow,
    )
    assert len(kept) == 2
    assert all("nasa.gov" in k["url"] or "usgs.gov" in k["url"] for k in kept)


def test_disabled_allowlist_keeps_hosts():
    assert is_allowed_osint_hit(
        {"url": "https://example.com/a"},
        enabled=False,
        allow=frozenset({"nasa.gov"}),
    )
