"""Unit tests for Osiris → SearXNG query forge (collector)."""

from thot.tools.collector.forge import (
    forge_queries_from_osiris_data,
    forge_searx_query,
    sharpen_query,
)


def test_forge_skips_bare_coords():
    q = forge_searx_query(
        title="Wildfire thermal anomaly -10.8 15.5",
        type_hint="wildfire fire",
        extra="NASA FIRMS",
    )
    assert "-10.8" not in q
    assert "15.5" not in q
    assert "Wildfire" in q or "wildfire" in q.lower()


def test_forge_from_fires_bucket():
    queries = forge_queries_from_osiris_data(
        {
            "fires": [
                {
                    "id": "f1",
                    "lat": -10.8,
                    "lng": 15.5,
                    "brightness": 320,
                }
            ]
        },
        max_queries=3,
    )
    assert len(queries) == 1
    assert queries[0]["coords"] == [-10.8, 15.5]
    assert "-10.8" not in queries[0]["query"]
    assert "-porn" in queries[0]["query"].lower()


def test_sharpen_adds_exclusions():
    s = sharpen_query("fires", "wildfire hotspot")
    assert "FIRMS" in s or "firms" in s.lower() or "NASA" in s
    assert "-porn" in s.lower()
