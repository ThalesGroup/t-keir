"""Title: Query expander and ontology scorer unit tests.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from thot.tools.search.business_ontology import (
    BusinessConcept,
    BusinessOntology,
    business_ontology_from_data,
)
from thot.tools.search.ontology_scorer import (
    OntologyMatchWeights,
    OntologyScorer,
    OntologyScorerConfig,
)
from thot.tools.search.query_expander import (
    ExpansionWeights,
    QueryExpander,
)


class _FoldNormalizer:
    def normalize(self, text: str) -> str:
        return " ".join((text or "").lower().split())


def _sample_ontology() -> BusinessOntology:
    concepts = [
        BusinessConcept(
            concept_id="ML",
            preferred_label="machine learning",
            synonyms=["ML"],
            surface_forms=["statistical learning"],
            broader=["AI"],
            narrower=["NN"],
            related=[],
        ),
        BusinessConcept(
            concept_id="NN",
            preferred_label="neural network",
            synonyms=["ANN"],
            surface_forms=[],
            broader=["ML"],
            narrower=[],
            related=[],
        ),
        BusinessConcept(
            concept_id="AI",
            preferred_label="artificial intelligence",
            synonyms=["AI"],
            surface_forms=[],
            broader=[],
            narrower=["ML"],
            related=[],
        ),
    ]
    ontology = BusinessOntology(concepts)
    ontology.build_label_index(_FoldNormalizer())
    return ontology


def test_business_ontology_from_query_payload():
    ontology = business_ontology_from_data(
        {
            "concepts": [
                {
                    "concept_id": "ML",
                    "preferred_label": "machine learning",
                    "synonyms": ["ML"],
                }
            ]
        }
    )
    assert "ML" in ontology.concepts
    assert business_ontology_from_data(None).concepts == {}


def test_query_expander_adds_related_terms():
    ontology = _sample_ontology()
    expander = QueryExpander(
        ontology,
        _FoldNormalizer(),  # type: ignore[arg-type]
        weights=ExpansionWeights(),
        max_terms_per_relation=5,
        enabled=True,
    )
    result = expander.expand("machine learning")
    assert "ML" in result.concept_ids
    relations = {term.relation for term in result.terms}
    assert "original" in relations
    assert "narrower" in relations or "synonyms" in relations


def test_ontology_scorer_exact_and_neutral():
    ontology = _sample_ontology()
    scorer = OntologyScorer(
        ontology,
        _FoldNormalizer(),  # type: ignore[arg-type]
        OntologyScorerConfig(
            enabled=True,
            match_weights=OntologyMatchWeights(),
            neutral_score=0.5,
        ),
    )
    assert scorer.score([], ["ML"]) == 0.5
    assert scorer.score(["ML"], ["ML"]) == 1.0
    narrower = scorer.score(["ML"], ["NN"])
    assert 0.0 < narrower <= 1.0


def test_ontology_scorer_extracts_json_ld_labels():
    ontology = _sample_ontology()
    scorer = OntologyScorer(
        ontology,
        _FoldNormalizer(),  # type: ignore[arg-type]
        OntologyScorerConfig(),
    )
    concepts = scorer.extract_document_concepts(
        '{"name": "machine learning", "label": "other term"}'
    )
    assert "ML" in concepts
