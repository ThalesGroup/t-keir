# -*- coding: utf-8 -*-
"""Tests for RAG runtime configuration loading."""

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
    assert config.search.ranking_profile == "hybrid_2_level"


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
