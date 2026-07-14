# -*- coding: utf-8 -*-
"""Tests for RAG runtime configuration loading."""

from thot.tools.search.rag_config import (
    load_rag_config,
    ontology_settings_from_mapping,
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
    assert isinstance(config.search.enabled, bool)
    assert config.search.ranking_profile == "hybrid_2_level"


def test_ontology_settings_from_mapping_overrides_defaults():
    settings = ontology_settings_from_mapping({"min_keyword_length": 4})
    assert settings.min_keyword_length == 4
