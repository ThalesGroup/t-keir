"""Unit tests for long-query ontology enrichment (eval path)."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

from thot.tasks.answer_generation.query_enrichment import (
    enrich_first_stage_runs,
)
from thot.tools.search.rag_config import load_rag_config


class _Fold:
    def normalize(self, text: str) -> str:
        return " ".join((text or "").lower().split())


def test_enrich_skips_short_single_sentence_queries():
    corpus = {"d1": {"title": "ML", "text": "machine learning"}}
    queries = {"q1": "machine learning"}  # 1 sentence, few tokens
    first = {"q1": {"d1": 1.0}}
    ontology = {
        "concepts": [
            {
                "concept_id": "ML",
                "preferred_label": "machine learning",
                "synonyms": ["ML"],
            }
        ]
    }
    with patch(
        "thot.tools.search.text_normalizer.normalizer_for_language",
        return_value=_Fold(),
    ):
        out = enrich_first_stage_runs(
            corpus,
            queries,
            first,
            ontology_payload=ontology,
        )
    assert out == first


def test_enrich_runs_expander_and_rescorer_for_long_query():
    corpus = {
        "weak": {"title": "", "text": "unrelated cooking recipes"},
        "strong": {
            "title": "",
            "text": "machine learning and neural networks",
        },
    }
    # Multi-sentence → triggers min_sentences even if under min_tokens.
    long_q = (
        "Statistical methods improve outcomes. "
        "Clinicians should reconsider protocols carefully today."
    )
    queries = {"q1": long_q}
    first = {"q1": {"weak": 1.0, "strong": 1.0}}
    ontology = {
        "concepts": [
            {
                "concept_id": "ML",
                "preferred_label": "machine learning",
                "synonyms": ["statistical methods", "statistical learning"],
                "narrower": ["NN"],
            },
            {
                "concept_id": "NN",
                "preferred_label": "neural network",
                "synonyms": ["ANN"],
                "broader": ["ML"],
            },
        ]
    }

    base = load_rag_config()
    scoring = replace(base.dual_hybrid.ontology_scoring, enabled=True)
    dual = replace(base.dual_hybrid, ontology_scoring=scoring)
    cfg = replace(base, dual_hybrid=dual)

    with (
        patch(
            "thot.tasks.answer_generation.query_enrichment._load_query_pipeline_runner",
            return_value=None,
        ),
        patch(
            "thot.tools.search.text_normalizer.normalizer_for_language",
            return_value=_Fold(),
        ),
        patch(
            "thot.tools.search.rag_config.load_rag_config",
            return_value=cfg,
        ),
    ):
        out = enrich_first_stage_runs(
            corpus,
            queries,
            first,
            ontology_payload=ontology,
        )

    ranked = list(out["q1"].keys())
    assert ranked[0] == "strong"
    assert out["q1"]["strong"] >= out["q1"]["weak"]
