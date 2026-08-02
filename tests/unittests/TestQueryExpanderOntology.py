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
        _FoldNormalizer(),
        weights=ExpansionWeights(),
        max_terms_per_relation=5,
        enabled=True,
    )
    result = expander.expand("machine learning")
    assert "ML" in result.concept_ids
    relations = {term.relation for term in result.terms}
    assert "original" in relations
    assert "narrower" in relations or "synonyms" in relations


def test_query_expander_nlp_seeds_expand_neighborhood():
    """NER/SVO-style seeds resolve and pull in narrower/broader concept ids."""
    ontology = _sample_ontology()
    expander = QueryExpander(
        ontology,
        _FoldNormalizer(),
        weights=ExpansionWeights(),
        max_terms_per_relation=5,
        enabled=True,
    )
    # Long claim: raw string may not phrase-match; NLP seed does.
    result = expander.expand(
        "Recent clinical studies suggest that statistical methods "
        "improve patient outcomes in oncology trials.",
        seed_labels=["statistical learning", "neural network"],
    )
    assert "ML" in result.concept_ids
    # Neighborhood: narrower NN and broader AI from ML.
    assert "NN" in result.concept_ids
    assert "AI" in result.concept_ids
    labels = {term.text.lower() for term in result.terms}
    assert "neural network" in labels or "ann" in labels
    assert "artificial intelligence" in labels or "ai" in labels


def test_query_expander_seed_only_without_query_match():
    ontology = _sample_ontology()
    expander = QueryExpander(
        ontology,
        _FoldNormalizer(),
        weights=ExpansionWeights(),
        enabled=True,
    )
    result = expander.expand(
        "what does this mean for the field?",
        seed_labels=["ANN"],
    )
    assert "NN" in result.concept_ids
    assert "ML" in result.concept_ids  # broader of NN


def test_nlp_seed_expansion_gate():
    from thot.tools.search.passage_retrieval import (
        _nlp_seed_expansion_applies,
        _nlp_seed_labels,
        _query_sentence_count,
        _query_token_count,
    )

    short = "machine learning benefits"
    multi = "First claim about aging. Second claim about lifespan."
    long = (
        "Recent clinical studies suggest that statistical methods "
        "improve patient outcomes in oncology trials worldwide today "
        "and clinicians should reconsider standard protocols carefully "
        "before adopting experimental treatments in practice settings "
        "across multiple hospital networks and outpatient clinics"
    )
    assert _query_token_count(short) < 32
    assert _query_sentence_count(multi) >= 2
    assert _query_token_count(long) >= 32
    # When enabled, always expand from analyzed NER/kg/keywords (any length).
    assert _nlp_seed_expansion_applies(
        short, enabled=True, min_tokens=32, min_sentences=2
    )
    assert _nlp_seed_expansion_applies(
        multi, enabled=True, min_tokens=32, min_sentences=2
    )
    assert _nlp_seed_expansion_applies(
        long, enabled=True, min_tokens=32, min_sentences=2
    )
    assert not _nlp_seed_expansion_applies(
        long, enabled=False, min_tokens=32, min_sentences=2
    )
    seeds = _nlp_seed_labels(
        {
            "ner_entities": [{"text": "AIS", "label": "misc"}],
            "keywords": ["dark activity"],
            "svo_triples": [
                {
                    "subject": "MT RED SEA EAGLE",
                    "verb": "disabled",
                    "object": "AIS transmitter",
                }
            ],
        },
        [],
    )
    assert "AIS" in seeds
    assert "dark activity" in seeds
    assert "MT RED SEA EAGLE" in seeds
    assert "AIS transmitter" in seeds


def test_nlp_seed_expansion_config_loaded():
    from thot.tools.search.rag_config import load_rag_config

    cfg = load_rag_config().dual_hybrid.query_expansion.nlp_seed_expansion
    assert cfg.enabled is True
    assert cfg.min_tokens >= 1


def test_short_query_nlp_seeds_expand_ontology_concepts():
    """Short analyst queries still expand ontology_concepts via NER/kg seeds."""
    ontology = _sample_ontology()
    expander = QueryExpander(
        ontology,
        _FoldNormalizer(),
        weights=ExpansionWeights(),
        enabled=True,
    )
    from thot.tools.search.passage_retrieval import _nlp_seed_labels

    analysis = {
        "ner_entities": [{"text": "neural network", "label": "misc"}],
        "keywords": ["ANN"],
        "svo_triples": [
            {
                "subject": "model",
                "verb": "uses",
                "object": "statistical learning",
            }
        ],
    }
    seeds = _nlp_seed_labels(analysis, [])
    result = expander.expand("what about AIS?", seed_labels=seeds)
    assert "NN" in result.concept_ids or "ML" in result.concept_ids


def test_ontology_scoring_config_loaded():
    from thot.tools.search.rag_config import load_rag_config

    cfg = load_rag_config().dual_hybrid.ontology_scoring
    assert cfg.enabled is False
    assert float(cfg.rescore_weight) > 0.0


def test_ontology_scorer_exact_and_neutral():
    ontology = _sample_ontology()
    scorer = OntologyScorer(
        ontology,
        _FoldNormalizer(),
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


def test_ontology_rescorer_blends_and_reorders():
    from thot.tools.search.ontology_scorer import OntologyRescorer

    ontology = _sample_ontology()
    scorer = OntologyScorer(
        ontology,
        _FoldNormalizer(),
        OntologyScorerConfig(
            enabled=True,
            match_weights=OntologyMatchWeights(),
            neutral_score=0.5,
        ),
    )
    rescorer = OntologyRescorer(scorer, weight=0.5)
    ranked = rescorer.rescore(
        ["ML"],
        [
            ("weak", 1.0, []),  # no concepts → neutral ontology
            ("strong", 1.0, ["ML"]),  # exact match
        ],
    )
    assert ranked[0][0] == "strong"


def test_ontology_rescorer_disabled_keeps_first_stage():
    from thot.tools.search.ontology_scorer import OntologyRescorer

    ontology = _sample_ontology()
    scorer = OntologyScorer(
        ontology,
        _FoldNormalizer(),
        OntologyScorerConfig(enabled=False),
    )
    rescorer = OntologyRescorer(scorer, weight=0.5)
    ranked = rescorer.rescore(
        ["ML"],
        [("a", 0.2, ["ML"]), ("b", 0.9, [])],
    )
    assert [doc for doc, _ in ranked] == ["b", "a"]


def test_ontology_scorer_extracts_json_ld_labels():
    ontology = _sample_ontology()
    scorer = OntologyScorer(
        ontology,
        _FoldNormalizer(),
        OntologyScorerConfig(),
    )
    concepts = scorer.extract_document_concepts(
        '{"name": "machine learning", "label": "other term"}'
    )
    assert "ML" in concepts


def test_query_expander_paraphrase_bridges():
    from thot.tools.search.business_ontology import ParaphraseBridge

    ontology = BusinessOntology(
        [
            BusinessConcept(
                concept_id="AGING",
                preferred_label="aging",
                synonyms=[],
                paraphrase_bridges=[
                    ParaphraseBridge(
                        claim="slows aging",
                        document="life span extension",
                    )
                ],
            )
        ]
    )
    ontology.build_label_index(_FoldNormalizer())
    expander = QueryExpander(
        ontology,
        _FoldNormalizer(),
        weights=ExpansionWeights(),
        enabled=True,
    )
    result = expander.expand("treatment slows aging in mice")
    assert "AGING" in result.concept_ids
    paraphrase = [t.text for t in result.terms if t.relation == "paraphrase"]
    assert "life span extension" in paraphrase


def test_ontology_scorer_prefers_chunk_concept_ids():
    ontology = business_ontology_from_data(None)
    scorer = OntologyScorer(
        ontology,
        _FoldNormalizer(),
        OntologyScorerConfig(enabled=True),
    )
    concepts = scorer.concepts_for_hit(
        "doc-1",
        json_ld="",
        concept_ids=["CAUSAL_POSITIVE"],
        linked_concept_ids=["DIRECTIONALITY"],
    )
    assert concepts == ["CAUSAL_POSITIVE", "DIRECTIONALITY"]
    assert scorer.score(["causal_positive"], concepts) == 1.0


def test_chunk_ontology_fields_from_document_and_external():
    from thot.tools.search.chunk_ontology import chunk_ontology_fields

    document = {
        "source_doc_id": "d1",
        "title": "Metabolism",
        "document_ontology": {
            "json_ld": (
                '{"@graph":[{"identifier":"DOC_CONCEPT",'
                '"name":"lipogenesis"}]}'
            )
        },
    }
    chunk = {
        "chunk_id": "c1",
        "text_raw": "suppression of 6PGD increased lipogenesis",
    }
    payload = {
        "concepts": [
            {
                "concept_id": "CAUSAL_POSITIVE",
                "preferred_label": "increases",
                "synonyms": ["increased"],
            }
        ]
    }
    fields = chunk_ontology_fields(chunk, document, ontology_payload=payload)
    assert "CAUSAL_POSITIVE" in fields["concept_ids"]
    assert fields["ontology_text"]


def test_extract_svo_and_ner_labels_use_pipeline_kg_shape():
    """Pipeline kg uses subject/property/value + content arrays, not text."""
    from thot.tools.search.chunk_ontology import (
        extract_ner_concept_labels,
        extract_svo_concept_labels,
    )

    document = {
        "source_doc_id": "d1",
        "content_ner": [
            {"text": "Greece", "label": "location"},
            {"text": "MT RED SEA EAGLE", "label": "misc"},
        ],
        "kg": [
            {
                "subject": {
                    "content": ["MARITIME", "ANALYTICS", "ALERT"],
                    "lemma_content": ["MARITIME", "ANALYTICS", "alert"],
                },
                "property": {"content": ["held"]},
                "value": {"content": ["station"]},
                "field_type": "content",
                "provenance": "document",
            }
        ],
    }
    svo = extract_svo_concept_labels(document)
    assert "MARITIME ANALYTICS ALERT" in svo
    assert "station" in svo
    ner = extract_ner_concept_labels(document)
    assert "Greece" in ner
    assert "MT RED SEA EAGLE" in ner


def test_chunk_ontology_external_requires_chunk_not_title():
    """Title-only ontology hits must not tag an unrelated chunk."""
    from thot.tools.search.chunk_ontology import chunk_ontology_fields

    document = {
        "source_doc_id": "d1",
        "title": "FoxO3a transcription factor overview",
    }
    chunk = {
        "chunk_id": "c1",
        "text_raw": "Unrelated paragraph about stock markets and volatility.",
    }
    payload = {
        "concepts": [
            {
                "concept_id": "FOXO3A",
                "preferred_label": "FoxO3a",
                "synonyms": ["FOXO3"],
                "related": ["AGING"],
            },
            {
                "concept_id": "AGING",
                "preferred_label": "aging",
                "synonyms": ["senescence"],
            },
        ]
    }
    fields = chunk_ontology_fields(chunk, document, ontology_payload=payload)
    assert "FOXO3A" not in fields["concept_ids"]
    assert "AGING" not in fields["linked_concept_ids"]


def test_chunk_ontology_linked_needs_chunk_evidence():
    """Linked neighbors without surface evidence in the chunk are dropped."""
    from thot.tools.search.chunk_ontology import chunk_ontology_fields

    document = {"source_doc_id": "d1", "title": "x"}
    chunk = {
        "chunk_id": "c1",
        "text_raw": "FoxO3a regulates apoptosis in cancer cells.",
    }
    payload = {
        "concepts": [
            {
                "concept_id": "FOXO3A",
                "preferred_label": "FoxO3a",
                "related": ["AGING", "APOPTOSIS"],
            },
            {
                "concept_id": "AGING",
                "preferred_label": "aging",
            },
            {
                "concept_id": "APOPTOSIS",
                "preferred_label": "apoptosis",
            },
        ]
    }
    fields = chunk_ontology_fields(chunk, document, ontology_payload=payload)
    assert "FOXO3A" in fields["concept_ids"]
    # Apoptosis appears in the chunk → direct or linked, but present.
    all_ids = set(fields["concept_ids"]) | set(fields["linked_concept_ids"])
    assert "APOPTOSIS" in all_ids
    # Aging has no surface form in the chunk → must not be attached.
    assert "AGING" not in all_ids


def test_chunk_ontology_expands_bridges_not_synonym_flood():
    """Hubs skip expansion; other concepts keep preferred + bridges only."""
    from thot.tools.search.chunk_ontology import chunk_ontology_fields

    document = {"source_doc_id": "d1"}
    chunk = {
        "chunk_id": "c1",
        "text_raw": "Aspirin suppresses PGE2 production in tumors.",
    }
    payload = {
        "concepts": [
            {
                "concept_id": "CAUSAL_NEGATIVE",
                "preferred_label": "inhibits",
                "synonyms": ["suppresses", "blocks", "impairs"],
                "paraphrase_bridges": [
                    {"claim": "inhibits PGE2", "document": "COX-2 knockout"}
                ],
            },
            {
                "concept_id": "ASPIRIN",
                "preferred_label": "aspirin",
                "synonyms": ["ASA", "acetylsalicylic acid"],
                "paraphrase_bridges": [
                    {"claim": "aspirin", "document": "acetylsalicylic acid"}
                ],
            },
        ]
    }
    fields = chunk_ontology_fields(chunk, document, ontology_payload=payload)
    assert "CAUSAL_NEGATIVE" in fields["concept_ids"]
    assert "ASPIRIN" in fields["concept_ids"]
    labels = {lab.casefold() for lab in fields["expansion_labels"]}
    # Causal hub must not dump synonym flood.
    assert "blocks" not in labels
    assert "impairs" not in labels
    # Domain concept: preferred + bridge partner, not every synonym.
    assert "aspirin" in labels
    assert "acetylsalicylic acid" in labels
    assert "asa" not in labels


def test_enrich_sparse_helper_still_merges():
    """enrich_sparse remains available for experiments; not used in index path."""
    from thot.tools.search.bge_m3 import enrich_sparse

    base = {"101": 0.2, "the": 0.1}  # "the" dropped; tiny raw map
    out = enrich_sparse(
        base,
        text="Aspirin inhibits the production of PGE2.",
        ontology_labels=["cyclooxygenase", "PGE2"],
    )
    assert len(out) >= 4
    assert "aspirin" in out
    assert "pge2" in out
    assert "cyclooxygenase" in out
