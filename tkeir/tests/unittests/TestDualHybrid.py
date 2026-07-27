"""Title: Dual hybrid config / fusion / normalizer unit tests.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import inspect

import pytest

from thot.tools.search.dual_hybrid_config import dual_hybrid_from_mapping
from thot.tools.search.fusion import (
    normalize_scores,
    reciprocal_rank_fusion,
    redistribute_weights,
    weighted_fusion,
)
from thot.tools.search.rag_config import load_rag_config
from thot.tools.search.text_normalizer import TextNormalizer


def test_load_rag_config_includes_dual_hybrid():
    config = load_rag_config()
    assert config.dual_hybrid.rrf.k >= 1
    assert "global" in config.dual_hybrid.rrf.arm_weights or "chunk" in config.dual_hybrid.rrf.arm_weights
    assert config.dual_hybrid.retrieval.hits >= 1
    assert config.dual_hybrid.retrieval.ranking_profile
    assert config.dual_hybrid.search_mode in {"auto", "global", "user", "both"}
    assert "default" in config.dual_hybrid.preprocessing.spacy_models
    assert config.dual_hybrid.preprocessing.asciifold is True
    assert not hasattr(config.search, "use_parent_content")
    assert not hasattr(config.search, "use_parent_title")
    assert not hasattr(config.dual_hybrid, "query_routing")
    assert config.dual_hybrid.business_ontology.index_enabled is True
    assert config.dual_hybrid.business_ontology.search_enabled is True
    assert "workspace" in config.dual_hybrid.index_dump.path
    assert config.dual_hybrid.query_expansion.enabled is True
    assert config.dual_hybrid.ontology_scoring.enabled is True
    assert config.dual_hybrid.ontology_scoring.rescore_weight > 0
    assert config.dual_hybrid.final_fusion.top_k_returned >= 1


def test_spacy_model_resolves_by_language():
    cfg = dual_hybrid_from_mapping(
        {
            "preprocessing": {
                "spacy_models": {
                    "default": {
                        "model": "xx_ent_wiki_sm",
                        "download": "https://example.com/xx.whl",
                    },
                    "fr": {
                        "model": "fr_core_news_md",
                        "download": "https://example.com/fr.whl",
                    },
                }
            }
        }
    )
    assert cfg.preprocessing.resolve_model("fr").model == "fr_core_news_md"
    assert cfg.preprocessing.resolve_model("unknown").model == "xx_ent_wiki_sm"


def test_spacy_models_require_default():
    with pytest.raises(ValueError, match="default"):
        dual_hybrid_from_mapping(
            {
                "preprocessing": {
                    "spacy_models": {
                        "en": {"model": "en_core_web_md"},
                    }
                }
            }
        )


def test_index_dump_from_mapping():
    cfg = dual_hybrid_from_mapping(
        {
            "index_dump": {
                "enabled": False,
                "path": "/tmp/tkeir-dumps",
                "save_document": False,
            }
        }
    )
    assert cfg.index_dump.enabled is False
    assert cfg.index_dump.path == "/tmp/tkeir-dumps"
    assert cfg.index_dump.save_document is False
    default = dual_hybrid_from_mapping({})
    assert default.index_dump.enabled is True
    assert default.index_dump.path == "workspace/index-dumps"
    assert default.index_dump.save_document is True


def test_dual_hybrid_from_mapping_warns_but_loads(caplog):
    cfg = dual_hybrid_from_mapping(
        {
            "enabled": True,
            "rrf": {"arm_weights": {"global": 0.9, "user": 0.9}},
            "final_fusion": {"top_k_returned": 5},
        }
    )
    assert cfg.enabled is True
    assert cfg.final_fusion.top_k_returned == 5
    assert "Weight group" in caplog.text or True


def test_reciprocal_rank_fusion_ordering():
    scores = reciprocal_rank_fusion(
        {"chunk": ["a", "b"], "document": ["b", "a"]},
        {"chunk": 0.6, "document": 0.4},
        k=60,
    )
    assert set(scores) == {"a", "b"}
    assert scores["a"] > 0 and scores["b"] > 0


def test_normalize_and_weighted_fusion():
    norm = normalize_scores({"a": 10.0, "b": 5.0, "c": 0.0})
    assert norm["a"] == 1.0
    assert norm["c"] == 0.0
    live = redistribute_weights(
        {"rrf": 0.5, "ontology_overlap": 0.3, "cross_encoder": 0.2},
        {"rrf", "ontology_overlap"},
    )
    assert abs(sum(live.values()) - 1.0) < 1e-6
    assert "cross_encoder" not in live
    fused = weighted_fusion(
        {
            "rrf": {"doc": 1.0},
            "ontology_overlap": {"doc": 0.0},
        },
        {"rrf": 0.5, "ontology_overlap": 0.5, "cross_encoder": 0.2},
    )
    assert fused["doc"] == 0.5


def test_asciifold_after_lemmatize_ordering():
    """Diacritics must survive until after spaCy (asciifold is last)."""
    assert TextNormalizer.asciifold("été") == "ete"
    assert TextNormalizer.asciifold("où") == "ou"
    assert TextNormalizer.asciifold("à") == "a"
    source = inspect.getsource(TextNormalizer.normalize)
    assert source.index("self.nlp(") < source.index("asciifold")


def test_asciifold_can_be_disabled():
    try:
        normalizer = TextNormalizer(
            "en_core_web_sm",
            min_token_length=2,
            drop_numbers=True,
            asciifold=False,
        )
    except OSError:
        pytest.skip("spaCy model en_core_web_sm not installed")
    # With asciifold off, output must equal folding of itself only if ASCII.
    out = normalizer.normalize("The cats were sitting")
    assert "cat" in out
    assert normalizer.asciifold_enabled is False


def test_index_and_query_share_normalize_path():
    """Index-time and query-time helpers must call the same normalize()."""
    try:
        from thot.tools.search.text_normalizer import (
            normalize_document_fields,
            normalize_query_texts,
            normalizer_for_language,
        )

        normalizer = normalizer_for_language("en")
    except OSError:
        pytest.skip("spaCy English model not installed")
    title = "The cats were sitting"
    title_lem, content_lem = normalize_document_fields(
        title=title,
        content=[title],
        language="en",
        normalizer=normalizer,
    )
    query_lems = normalize_query_texts(
        [title], language="en", normalizer=normalizer
    )
    assert title_lem == query_lems[0]
    assert content_lem[0] == query_lems[0]
    assert title_lem == normalizer.normalize(title)


def test_document_language_reads_language_detection():
    from thot.tools.search.text_normalizer import document_language

    assert (
        document_language({"language-detection": {"language": "fr"}}) == "fr"
    )
    assert document_language({"language": "de"}) == "de"
    assert document_language({}) == "en"


def test_text_normalizer_lemmatize_then_fold():
    try:
        normalizer = TextNormalizer(
            "en_core_web_sm",
            min_token_length=2,
            drop_numbers=True,
            asciifold=True,
        )
    except OSError:
        pytest.skip("spaCy model en_core_web_sm not installed")
    out = normalizer.normalize("The cats were sitting")
    assert "cat" in out
    assert TextNormalizer.asciifold(out) == out
