"""Title: Rag Config

Tests for RAG runtime configuration loading.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.tools.search.rag_config import (
    RagPassageConfig,
    _passage_config_from_mapping,
    load_rag_config,
    ontology_settings_from_mapping,
    resolve_passage_settings,
)


def test_load_rag_config_reads_min_keyword_length():
    config = load_rag_config()
    assert config.ontology.min_keyword_length >= 1
    assert config.ontology.max_entities >= 1
    assert config.ontology.max_keywords >= 1
    assert config.prompt.chunk_context_mode in {
        "chunk_excerpts",
        "svo_ontology",
    }
    assert config.prompt.max_svo_triples >= 1
    assert config.prompt.passages.count >= 1
    assert config.prompt.passages.max_chars >= 200
    assert config.prompt.passages.context_sentences >= 0
    assert isinstance(config.search.enabled, bool)
    assert config.search.ranking_profile in {
        "auto",
        "hybrid_2_level",
        "hybrid_semantic",
        "hybrid_lexical",
    }
    assert isinstance(config.search.rerank.enabled, bool)
    assert isinstance(config.dual_hybrid.enabled, bool)
    assert config.dual_hybrid.rrf.k >= 1
    assert config.search.rerank.candidates >= 1
    assert config.search.rerank.strategy in {
        "cross_encoder",
        "embedding_cosine",
    }
    assert config.models.embedding_model
    assert config.models.reranker_model
    assert config.vespa.url.startswith("http")
    assert config.vespa.config_url.startswith("http")
    assert config.vespa.timeout_seconds >= 1.0
    assert config.vespa.concurrency.enrich_workers >= 1


def test_vespa_config_from_mapping():
    from thot.tools.search.rag_config import _vespa_config_from_mapping

    cfg = _vespa_config_from_mapping(
        {
            "url": "http://vespa:8080/",
            "config_url": "http://vespa:19071/",
            "timeout_seconds": 45,
            "concurrency": {"enrich_workers": 3},
        }
    )
    assert cfg.url == "http://vespa:8080"
    assert cfg.config_url == "http://vespa:19071"
    assert cfg.timeout_seconds == 45.0
    assert cfg.concurrency.enrich_workers == 3


def test_passage_config_from_nested_mapping():
    cfg = _passage_config_from_mapping(
        {
            "passages": {
                "count": 5,
                "max_chars": 2400,
                "context_sentences": 1,
            }
        }
    )
    assert cfg == RagPassageConfig(
        count=5, max_chars=2400, context_sentences=1
    )


def test_passage_config_from_legacy_flat_keys():
    cfg = _passage_config_from_mapping(
        {
            "max_focus_passages": 4,
            "max_chars_per_passage": 1200,
            "focus_context_sentences": 0,
        }
    )
    assert cfg == RagPassageConfig(
        count=4, max_chars=1200, context_sentences=0
    )


def test_resolve_passage_settings_applies_request_overrides():
    base = RagPassageConfig(count=3, max_chars=1800, context_sentences=2)
    resolved = resolve_passage_settings(
        defaults=base,
        count=6,
        max_chars=3000,
        context_sentences=1,
    )
    assert resolved == RagPassageConfig(
        count=6, max_chars=3000, context_sentences=1
    )


def test_ontology_settings_from_mapping_overrides_defaults():
    settings = ontology_settings_from_mapping({"min_keyword_length": 4})
    assert settings.min_keyword_length == 4
