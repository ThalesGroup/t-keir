"""Title: Long-query NLP + ontology enrichment for offline / BEIR retrieve.

Applies the same config-gated stages as :class:`PassageRetrievalPipeline`
when evaluating multi-query corpora (ArguAna-style document-as-query):

1. Query NLP (NER / keywords / SVO) when ``search.enabled``
2. Business-ontology resolve + neighborhood expansion
3. :class:`OntologyRescorer` on the first-stage candidate pool

Short queries (below ``nlp_seed_expansion.min_tokens``) skip this path so
SciFact-style leaderboard runs stay unchanged.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)


def enrich_first_stage_runs(
    corpus: dict[str, dict[str, str]] | dict[str, str],
    queries: dict[str, str],
    first_stage: dict[str, dict[str, float]],
    *,
    ontology_payload: dict[str, Any] | None,
    language: str = "en",
) -> dict[str, dict[str, float]]:
    """NLP + ontology expand + OntologyRescorer for long queries only.
    
    Args:
        corpus: BEIR-style corpus.
        queries: ``qid → text``.
        first_stage: RRF (or other) runs to re-score.
        ontology_payload: ``datasets/<name>/business_ontology.yaml`` content.
        language: Query NLP language.
    
    Returns:
        Possibly re-ordered / re-scored first-stage runs (same shape).
    
        Example:
            >>> from thot.tasks.answer_generation.query_enrichment import enrich_first_stage_runs
            >>> enrich_first_stage_runs({}, {}, {"q1": {}}, ontology_payload=None)
            {'q1': {}}
    """
    if not ontology_payload or not (ontology_payload.get("concepts") or []):
        return first_stage

    from thot.tools.eval.hybrid_retrieve import document_text
    from thot.tools.search.business_ontology import business_ontology_from_data
    from thot.tools.search.chunk_ontology import match_external_concepts
    from thot.tools.search.ontology_scorer import (
        OntologyMatchWeights,
        OntologyRescorer,
        OntologyScorer,
        OntologyScorerConfig,
    )
    from thot.tools.search.passage_retrieval import (
        _nlp_seed_expansion_applies,
        _nlp_seed_labels,
    )
    from thot.tools.search.query_expander import (
        ExpansionWeights,
        QueryExpander,
    )
    from thot.tools.search.rag_config import load_rag_config
    from thot.tools.search.text_normalizer import normalizer_for_language

    rag = load_rag_config()
    answer_gen = rag.answer_generation
    if not answer_gen.use_ontology:
        LOGGER.info(
            "Ontology enrichment skipped: answer_generation.use_ontology=false"
        )
        return first_stage

    dual = rag.dual_hybrid
    if not dual.business_ontology.search_enabled:
        return first_stage
    if not (dual.query_expansion.enabled or dual.ontology_scoring.enabled):
        return first_stage

    nlp_cfg = dual.query_expansion.nlp_seed_expansion
    long_qids = [
        qid
        for qid, qtext in queries.items()
        if _nlp_seed_expansion_applies(
            qtext,
            enabled=bool(nlp_cfg.enabled),
            min_tokens=int(nlp_cfg.min_tokens),
            min_sentences=int(getattr(nlp_cfg, "min_sentences", 2)),
        )
    ]
    if not long_qids:
        LOGGER.info(
            "Ontology enrichment skipped: no query ≥ min_tokens=%d "
            "or min_sentences=%d (nlp_seed_expansion)",
            int(nlp_cfg.min_tokens),
            int(getattr(nlp_cfg, "min_sentences", 2)),
        )
        return first_stage
    try:
        normalizer = normalizer_for_language(language or "en")
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Ontology enrichment: normalizer unavailable: %s", exc)
        return first_stage

    ontology = business_ontology_from_data(ontology_payload)
    if not ontology.concepts:
        return first_stage
    ontology.build_label_index(normalizer)

    expander = QueryExpander(
        ontology,
        normalizer,
        weights=ExpansionWeights(
            **{
                k: float(v)
                for k, v in dual.query_expansion.weights.items()
                if k
                in {
                    "original",
                    "synonyms",
                    "narrower",
                    "broader",
                    "related",
                    "paraphrase",
                }
            }
        ),
        max_terms_per_relation=dual.query_expansion.max_terms_per_relation,
        enabled=dual.query_expansion.enabled,
    )

    pipeline_runner = None
    if answer_gen.use_nlp and rag.search.enabled:
        pipeline_runner = _load_query_pipeline_runner()

    # Cache doc concepts for candidates that appear under long queries.
    doc_concepts_cache: dict[str, list[str]] = {}

    def _concepts_for_doc(doc_id: str) -> list[str]:
        cached = doc_concepts_cache.get(doc_id)
        if cached is not None:
            return cached
        if doc_id not in corpus:
            doc_concepts_cache[doc_id] = []
            return []
        ids, linked, _labels = match_external_concepts(
            document_text(corpus[doc_id]), ontology_payload
        )
        concepts = list(ids) + list(linked)
        doc_concepts_cache[doc_id] = concepts
        return concepts

    rescorer: OntologyRescorer | None = None
    if dual.ontology_scoring.enabled:
        mw = dual.ontology_scoring.match_weights or {}
        scorer = OntologyScorer(
            ontology,
            normalizer,
            OntologyScorerConfig(
                enabled=True,
                match_weights=OntologyMatchWeights(
                    exact=float(mw.get("exact", 1.0)),
                    synonym=float(mw.get("synonym", 0.9)),
                    narrower=float(mw.get("narrower", 0.6)),
                    broader=float(mw.get("broader", 0.3)),
                    shared_parent=float(mw.get("shared_parent", 0.2)),
                ),
                max_traversal_depth=int(
                    dual.ontology_scoring.max_traversal_depth
                ),
                normalize_by_query_concepts=bool(
                    dual.ontology_scoring.normalize_by_query_concepts
                ),
                neutral_score=float(
                    getattr(dual.fallback, "neutral_score", 0.5)
                ),
            ),
        )
        weight = float(
            getattr(dual.ontology_scoring, "rescore_weight", 0.13) or 0.13
        )
        rescorer = OntologyRescorer(scorer, weight=weight)

    out = {qid: dict(hits) for qid, hits in first_stage.items()}
    nlp_used = 0
    expanded = 0
    rescored = 0

    for qid in long_qids:
        qtext = queries.get(qid) or ""
        hits = out.get(qid) or {}
        if not hits:
            continue

        query_analysis: dict[str, Any] | None = None
        nlp_terms: list[str] = []
        if pipeline_runner is not None:
            query_analysis, nlp_terms = _analyze_query_nlp(
                pipeline_runner, qtext, language=language
            )
            if nlp_terms:
                nlp_used += 1

        seed_labels = _nlp_seed_labels(query_analysis, nlp_terms)
        expansion = expander.expand(qtext, seed_labels=seed_labels or None)
        concept_ids = list(expansion.concept_ids or [])
        if concept_ids:
            expanded += 1

        if rescorer is None or not concept_ids:
            continue

        ranked = rescorer.rescore(
            concept_ids,
            [
                (doc_id, float(score), _concepts_for_doc(doc_id))
                for doc_id, score in hits.items()
            ],
        )
        out[qid] = {doc_id: float(score) for doc_id, score in ranked}
        rescored += 1

    LOGGER.info(
        "Long-query ontology enrichment: candidates=%d nlp=%d "
        "expanded=%d ontology_rescore=%d (min_tokens=%d)",
        len(long_qids),
        nlp_used,
        expanded,
        rescored,
        int(nlp_cfg.min_tokens),
    )
    return out


def _load_query_pipeline_runner() -> Any | None:
    """Lazy-load PipelineRunner for query NLP (shared with passage search).
    
        Example:
            >>> from thot.tasks.answer_generation.query_enrichment import _load_query_pipeline_runner
            >>> callable(_load_query_pipeline_runner)
            True
    """
    try:
        from thot.tools.search.passage_retrieval import (
            _default_pipeline_runner,
        )

        return _default_pipeline_runner()
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Query NLP runner unavailable for enrichment: %s", exc)
        return None


def _analyze_query_nlp(
    runner: Any,
    query: str,
    *,
    language: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Run linguistic pipeline; return ``(analysis_dict, search_terms)``.
    
        Example:
            >>> from thot.tasks.answer_generation.query_enrichment import _analyze_query_nlp
            >>> callable(_analyze_query_nlp)
            True
    """
    try:
        from thot.tools.search.query_analyzer import (
            analyze_query_document,
            run_linguistic_pipeline,
        )
        from thot.tools.search.rag_config import load_rag_config

        processed = run_linguistic_pipeline(runner, query, language=language)
        analysis = analyze_query_document(
            processed,
            query,
            language=language,
            config=load_rag_config().search,
        )
        terms = [t for t in analysis.search_terms or [] if t][:48]
        payload = {
            "raw_query": analysis.raw_query,
            "search_terms": list(analysis.search_terms or []),
            "lemmas": list(analysis.lemmas or []),
            "keywords": list(analysis.keywords or []),
            "ner_entities": [
                getattr(e, "text", str(e)) for e in analysis.ner_entities or []
            ],
            "language": analysis.language,
        }
        return payload, terms
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Query NLP failed during enrichment: %s", exc)
        return None, []
