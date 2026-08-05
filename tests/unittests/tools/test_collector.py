"""Title: Collector unit tests

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from pathlib import Path

from thot.tools.collector.convert import (
    bytes_to_markdown,
    clean_markdown,
    format_collected_markdown,
)
from thot.tools.collector.searxng import normalize_searxng_results
from thot.tools.collector.service import markdown_filename
from thot.tools.collector.topics import (
    resolve_topic_ontology,
    workspace_topic_dir,
)


def test_clean_markdown_strips_controls():
    assert clean_markdown("a\x00b\n\n\nc") == "ab\n\nc"


def test_bytes_to_markdown_html():
    md = bytes_to_markdown(
        b"<html><body><h1>Hello</h1><p>World</p></body></html>",
        filename="x.html",
        content_type="text/html",
    )
    assert "Hello" in md or "World" in md


def test_format_collected_markdown_front_matter():
    md = format_collected_markdown(
        "# Hello\n\nBody paragraph.",
        title="Hello",
        source_url="https://ex.example/a",
        query="maritime",
        topic="osint",
        collected_at="2026-01-01T00:00:00Z",
    )
    assert md.startswith("---\n")
    assert "title: Hello" in md
    assert "source: https://ex.example/a" in md
    assert "query: maritime" in md
    assert "# Hello\n" in md
    # Duplicate heading from body is dropped.
    assert md.count("# Hello") == 1
    assert "Body paragraph." in md


def test_normalize_searxng_results():
    rows = normalize_searxng_results(
        {
            "results": [
                {"url": "https://a.example", "title": "A", "content": "x"},
                {"title": "missing-url"},
            ]
        }
    )
    assert len(rows) == 1
    assert rows[0]["url"] == "https://a.example"


def test_wrap_collect_results_table():
    from thot.tools.collector.service import wrap_collect_results

    row = {
        "correlation_id": "c1",
        "query": "q",
        "topic": None,
        "language_hint": None,
        "searxng_hits": 0,
        "documents": [{"markdown": "# Hi"}],
        "duplicates": [],
        "errors": [],
        "dedupe": {"index_size": 0, "max_hamming": 3, "path": "/x"},
        "started_at": "t0",
        "ended_at": "t1",
    }
    single = wrap_collect_results([row])
    assert list(single.keys()) == ["results"]
    assert len(single["results"]) == 1
    assert single["results"][0]["documents"][0]["markdown"] == "# Hi"
    batch = wrap_collect_results([row, {**row, "query": "q2"}])
    assert len(batch["results"]) == 2


def test_markdown_filename_stable():
    name = markdown_filename("https://ex.example/doc", "Hello World!")
    assert name.endswith(".md")
    assert "Hello_World" in name
    a = markdown_filename("https://ex.example/doc", "A")
    b = markdown_filename("https://ex.example/doc", "B")
    assert a.split("__", 1)[1] == b.split("__", 1)[1]


def test_resolve_topic_ontology_osint(tmp_path: Path):
    from thot.core.TkeirPaths import configs_dir

    catalog = Path(configs_dir()) / "collector" / "topics.yaml"
    spec = resolve_topic_ontology(
        "osint", catalog_path=catalog, workspace=tmp_path, language="en"
    )
    assert spec.topic == "osint"
    assert spec.business_ontology_dataset == "osint"
    assert spec.language == "en"


def test_workspace_topic_override(tmp_path: Path):
    from thot.core.TkeirPaths import configs_dir

    topic_dir = workspace_topic_dir("custom", workspace=tmp_path)
    topic_dir.mkdir(parents=True)
    (topic_dir / "business_ontology.yaml").write_text(
        "version: 1\nconcepts: []\n", encoding="utf-8"
    )
    onto = topic_dir / "ontologies"
    onto.mkdir()
    ttl = onto / "extra.ttl"
    ttl.write_text("@prefix : <http://ex/> .\n", encoding="utf-8")
    catalog = Path(configs_dir()) / "collector" / "topics.yaml"
    spec = resolve_topic_ontology(
        "custom", catalog_path=catalog, workspace=tmp_path
    )
    assert spec.business_ontology_path == topic_dir / "business_ontology.yaml"
    assert any(p.endswith("extra.ttl") for p in spec.ontology_paths)


def test_simhash_language_agnostic_accents():
    from thot.tools.collector.simhash import hamming_distance, simhash64

    a = simhash64(
        "The maritime AIS anomaly report describes spoofing near the Strait."
    )
    b = simhash64(
        "The maritime AIS anomaly report describes spoofing near the Strait!"
    )
    assert hamming_distance(a, b) <= 3
    assert simhash64("Café français") == simhash64("cafe francais")


def test_dedupe_index_url_and_simhash(tmp_path: Path):
    from thot.tools.collector.dedupe import CollectorDedupeIndex

    idx = CollectorDedupeIndex(tmp_path / "dedupe", max_hamming=3)
    body = ("Unique maritime content for simhash testing. " * 8).strip()
    first = idx.probe_and_register("https://a.example/doc", body)
    assert not first.is_duplicate
    assert idx.known_url("https://a.example/doc")
    url_dup = idx.probe_and_register("https://a.example/doc", body)
    assert url_dup.is_duplicate and url_dup.reason == "url"
    near = idx.probe_and_register("https://b.example/mirror", body + "!")
    assert near.is_duplicate and near.reason == "simhash"
    other = idx.probe_and_register(
        "https://c.example/other",
        (
            "Completely different scientific abstract about proteins. " * 8
        ).strip(),
    )
    assert not other.is_duplicate
    reloaded = CollectorDedupeIndex(tmp_path / "dedupe", max_hamming=3)
    assert reloaded.size >= 2
    assert reloaded.known_url("https://a.example/doc")


def test_collector_metrics_registered():
    from thot.core.ThotMetrics import ThotMetrics
    from thot.tools.collector.app import _ensure_collector_metrics

    _ensure_collector_metrics()
    assert "collector_http" in ThotMetrics.call_counter
    assert "collector_documents" in ThotMetrics.call_counter
    assert "collector_duplicates" in ThotMetrics.call_counter
    assert "collector_errors" in ThotMetrics.call_counter


def test_collector_intent_for_path():
    from thot.action.middleware import intent_for_path

    assert intent_for_path("/collect") == "collect"
    assert intent_for_path("/collect/batch") == "collect"
