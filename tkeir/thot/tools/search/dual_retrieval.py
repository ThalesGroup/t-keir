"""Title: Dual-granularity hybrid retrieval (chunk + document) with RRF fusion.

Orchestrates sequential Vespa arms (streaming-safe), ontology overlap,
optional cross-encoder, and final weighted fusion. All tunable values come
from ``dual_hybrid`` in ``rag.yaml``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from thot.tools.search.business_ontology import (
    BusinessOntology,
    business_ontology_from_data,
)
from thot.tools.search.dual_hybrid_config import DualHybridConfig
from thot.tools.search.fusion import (
    normalize_scores,
    reciprocal_rank_fusion,
    weighted_fusion,
)
from thot.tools.search.ontology_scorer import (
    OntologyMatchWeights,
    OntologyScorer,
    OntologyScorerConfig,
)
from thot.tools.search.query_expander import (
    ExpansionWeights,
    QueryExpander,
    QueryExpansionResult,
)
from thot.tools.search.rerank import rerank_scored_texts
from thot.tools.search.text_normalizer import (
    TextNormalizer,
    normalize_query_texts,
    normalizer_for_language,
)
from thot.tools.search.vespa_client import (
    VespaClient,
    build_multi_field_contains_or_clause,
    build_text_raw_contains_or_clause,
    escape_yql_literal,
)

LOGGER = logging.getLogger(__name__)


@dataclass
class DualHit:
    """One fused search result with score breakdown."""

    source_doc_id: str
    score: float
    scores: dict[str, float] = field(default_factory=dict)
    title: str = ""
    json_ld: str = ""
    best_chunk_text: str = ""
    chunk_id: str = ""


@dataclass
class DualSearchResult:
    """Pipeline output."""

    hits: list[DualHit]
    expansion: QueryExpansionResult | None = None
    timings_ms: dict[str, float] = field(default_factory=dict)
    active_signals: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)


class DualHybridPipeline:
    """Two-arm Vespa retrieval + RRF + ontology + cross-encoder."""

    def __init__(
        self,
        config: DualHybridConfig,
        vespa: VespaClient,
        *,
        llm: Any | None = None,
    ) -> None:
        self.config = config
        self.vespa = vespa
        self.llm = llm
        LOGGER.info(
            "DualHybridPipeline ready enabled=%s chunk_profile=%s "
            "document_profile=%s asciifold=%s",
            config.enabled,
            config.retrieval.chunk.profile,
            config.retrieval.document.profile,
            config.preprocessing.asciifold,
        )

    def _normalizer_for(self, language: str | None) -> TextNormalizer | None:
        try:
            # Prefer config already loaded on the pipeline; fall back to rag.yaml.
            return TextNormalizer.for_language(
                self.config.preprocessing, language
            )
        except Exception as exc:  # noqa: BLE001
            try:
                return normalizer_for_language(language)
            except Exception:  # noqa: BLE001
                LOGGER.warning(
                    "TextNormalizer unavailable language=%s: %s", language, exc
                )
                return None

    def _bind_ontology(
        self,
        *,
        language: str | None,
        business_ontology: Any | None,
        degraded: list[str],
    ) -> tuple[TextNormalizer | None, QueryExpander | None, OntologyScorer]:
        """Resolve per-request normalizer, expander, and scorer."""
        normalizer = self._normalizer_for(language)
        if normalizer is None:
            degraded.append("text_normalizer")

        ontology = business_ontology_from_data(business_ontology)
        if normalizer is not None and ontology.concepts:
            ontology.build_label_index(normalizer)
        elif not ontology.concepts:
            degraded.append("business_ontology")

        expander: QueryExpander | None = None
        if normalizer is not None:
            expander = QueryExpander(
                ontology,
                normalizer,
                weights=ExpansionWeights(
                    **{
                        key: float(value)
                        for key, value in self.config.query_expansion.weights.items()
                        if key
                        in {
                            "original",
                            "synonyms",
                            "narrower",
                            "broader",
                            "related",
                        }
                    }
                ),
                max_terms_per_relation=(
                    self.config.query_expansion.max_terms_per_relation
                ),
                enabled=self.config.query_expansion.enabled
                and bool(ontology.concepts),
            )

        match = self.config.ontology_scoring.match_weights
        scorer = OntologyScorer(
            ontology,
            normalizer or _IdentityNormalizer(),
            OntologyScorerConfig(
                enabled=self.config.ontology_scoring.enabled
                and bool(ontology.concepts),
                match_weights=OntologyMatchWeights(
                    exact=float(match.get("exact", 1.0)),
                    synonym=float(match.get("synonym", 0.9)),
                    narrower=float(match.get("narrower", 0.6)),
                    broader=float(match.get("broader", 0.3)),
                    shared_parent=float(match.get("shared_parent", 0.2)),
                ),
                max_traversal_depth=(
                    self.config.ontology_scoring.max_traversal_depth
                ),
                normalize_by_query_concepts=(
                    self.config.ontology_scoring.normalize_by_query_concepts
                ),
                neutral_score=self.config.fallback.neutral_score,
            ),
        )
        return normalizer, expander, scorer

    async def search(
        self,
        query: str,
        *,
        user_space: str,
        language: str | None = None,
        business_ontology: Any | None = None,
        q_chunk_emb: list[float] | None = None,
        q_question_emb: list[float] | None = None,
        top_k: int | None = None,
    ) -> DualSearchResult:
        """Run the full dual-retrieval pipeline.

        Args:
            query: Raw user query.
            user_space: Vespa streaming group.
            language: Detected / request language for spaCy model selection.
            business_ontology: Per-request concepts (list or ``{concepts:[]}``).
            q_chunk_emb: Optional chunk embedding.
            q_question_emb: Optional question embedding.
            top_k: Override ``final_fusion.top_k_returned`` (e.g. BEIR eval).
        """
        timings: dict[str, float] = {}
        degraded: list[str] = []
        t0 = time.perf_counter()
        return_k = (
            max(1, int(top_k))
            if top_k is not None
            else self.config.final_fusion.top_k_returned
        )

        normalizer, expander, scorer = self._bind_ontology(
            language=language,
            business_ontology=business_ontology,
            degraded=degraded,
        )

        if expander is not None:
            expansion = expander.expand(query)
        elif normalizer is not None:
            # No ontology: still normalize the query for the document arm.
            from thot.tools.search.query_expander import (
                ExpandedTerm,
                QueryExpansionResult,
            )

            normalized = normalizer.normalize(query)
            expansion = QueryExpansionResult(
                terms=[
                    ExpandedTerm(
                        text=query.strip(),
                        weight=1.0,
                        relation="original",
                        normalized_text=normalized,
                    )
                ],
                concept_ids=[],
                raw_query=query,
                normalized_query=normalized,
            )
        else:
            from thot.tools.search.query_expander import (
                ExpandedTerm,
                QueryExpansionResult,
            )

            expansion = QueryExpansionResult(
                terms=[
                    ExpandedTerm(
                        text=query, weight=1.0, relation="original"
                    )
                ],
                concept_ids=[],
                raw_query=query,
                normalized_query=query,
            )
            degraded.append("query_normalization_skipped")
        timings["expand"] = (time.perf_counter() - t0) * 1000

        from thot.tools.search.lexical_signal import (
            is_long_query,
            lexical_query_projection,
            near_copy_penalty,
            rare_token_multiplier,
        )

        long_query = is_long_query(query)
        bm25_projection = lexical_query_projection(query)
        # Document-as-query: prefer semantic chunk profile + chunk arm weight.
        chunk_profile = self.config.retrieval.chunk.profile
        arm_weights = dict(self.config.rrf.arm_weights)
        fusion_weights = dict(self.config.final_fusion.weights)
        rerank_strategy = "cross_encoder"
        rerank_query = query
        if long_query:
            chunk_profile = "hybrid_semantic"
            arm_weights = {"chunk": 0.75, "document": 0.25}
            # Lexical on long arguments rewards near-copies; lean on RRF +
            # cheap embedding cosine (full CE on long queries is too slow).
            fusion_weights = {
                "rrf": 0.45,
                "lexical_overlap": 0.10,
                "ontology_overlap": 0.15,
                "cross_encoder": 0.30,
            }
            rerank_strategy = "embedding_cosine"
            rerank_query = bm25_projection or query[:400]
            degraded.append("long_query_semantic")

        t1 = time.perf_counter()
        # Sequential arms: Vespa streaming mode often 504s when two
        # nearestNeighbor/BM25 visitors hit the same group concurrently.
        chunk_rank, chunk_meta = await self._search_chunks(
            expansion,
            user_space,
            q_chunk_emb,
            q_question_emb,
            bm25_projection=bm25_projection,
            ranking_profile=chunk_profile,
        )
        doc_rank, doc_meta = await self._search_documents(
            expansion,
            user_space,
            normalizer,
            language,
            bm25_projection=bm25_projection,
        )
        timings["vespa_arms"] = (time.perf_counter() - t1) * 1000

        t2 = time.perf_counter()
        rrf_raw = reciprocal_rank_fusion(
            {"chunk": chunk_rank, "document": doc_rank},
            arm_weights,
            self.config.rrf.k,
        )
        rrf_norm = normalize_scores(rrf_raw)
        fused_ids = sorted(
            rrf_norm, key=rrf_norm.get, reverse=True  # type: ignore[arg-type]
        )[: self.config.rrf.top_n_after_fusion]
        timings["rrf"] = (time.perf_counter() - t2) * 1000

        t3 = time.perf_counter()
        ont_scores: dict[str, float] = {}
        doc_fields: dict[str, dict[str, Any]] = {}
        for doc_id in fused_ids:
            meta = doc_meta.get(doc_id) or chunk_meta.get(doc_id) or {}
            json_ld = str(meta.get("json_ld") or "")
            if not json_ld and doc_id in chunk_meta:
                try:
                    fields = await self.vespa.get_document_by_ref(
                        str(chunk_meta[doc_id].get("doc_ref") or "")
                    )
                    json_ld = str(fields.get("json_ld") or "")
                    meta = {**meta, **fields, "json_ld": json_ld}
                except Exception:  # noqa: BLE001
                    degraded.append(f"json_ld:{doc_id}")
            doc_fields[doc_id] = meta
            concepts = scorer.concepts_for_document(doc_id, json_ld)
            ont_scores[doc_id] = scorer.score(
                expansion.concept_ids, concepts
            )
        ont_norm = normalize_scores(ont_scores)
        timings["ontology"] = (time.perf_counter() - t3) * 1000

        t4 = time.perf_counter()
        ce_norm: dict[str, float] = {}
        active = {"rrf", "ontology_overlap", "lexical_overlap"}
        # Prefer title + chunk text for cross-encoder (more signal than chunk alone).
        if self.config.cross_encoder.enabled and self.llm is not None and fused_ids:
            top_m = fused_ids[: self.config.cross_encoder.top_m]
            text_items: list[tuple[str, float]] = []
            text_to_doc: dict[str, str] = {}
            for doc_id in top_m:
                cmeta = chunk_meta.get(doc_id) or {}
                dmeta = doc_fields.get(doc_id) or {}
                title = str(dmeta.get("title") or "")
                chunk_text = str(cmeta.get("best_chunk_text") or "")
                passage = "\n".join(part for part in (title, chunk_text) if part)
                max_chars = max(
                    120, int(self.config.cross_encoder.max_length) * 4
                )
                text = (passage or title or chunk_text or doc_id)[:max_chars]
                unique_text = (
                    text if text not in text_to_doc else f"{text}\n#{doc_id}"
                )
                text_to_doc[unique_text] = doc_id
                text_items.append(
                    (unique_text, float(rrf_norm.get(doc_id, 0.0)))
                )
            try:
                ranked = await rerank_scored_texts(
                    self.llm,
                    rerank_query,
                    text_items,
                    strategy=rerank_strategy,
                )
                ce_raw = {
                    text_to_doc[text]: float(score)
                    for text, score in ranked
                    if text in text_to_doc
                }
                ce_norm = normalize_scores(ce_raw)
                active.add("cross_encoder")
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Cross-encoder failed: %s", exc)
                degraded.append("cross_encoder")
        else:
            if not self.config.cross_encoder.enabled:
                degraded.append("cross_encoder_disabled")
        timings["cross_encoder"] = (time.perf_counter() - t4) * 1000

        t5 = time.perf_counter()
        from thot.tools.search.lexical_signal import lexical_overlap_score

        lex_raw: dict[str, float] = {}
        for doc_id in fused_ids:
            cmeta = chunk_meta.get(doc_id) or {}
            dmeta = doc_fields.get(doc_id) or {}
            title = str(dmeta.get("title") or "")
            body = str(
                cmeta.get("best_chunk_text")
                or " ".join(
                    str(x)
                    for x in (dmeta.get("content") or [])
                    if x
                )
                or ""
            )
            score = lexical_overlap_score(query, title=title, body=body)
            if self.config.final_fusion.near_copy_penalty:
                score *= near_copy_penalty(
                    query, f"{title} {body}".strip()
                )
            score *= rare_token_multiplier(query, title=title, body=body)
            lex_raw[doc_id] = score
        lex_norm = normalize_scores(lex_raw)
        timings["lexical"] = (time.perf_counter() - t5) * 1000

        signals = {
            "rrf": {doc_id: rrf_norm.get(doc_id, 0.0) for doc_id in fused_ids},
            "ontology_overlap": {
                doc_id: ont_norm.get(
                    doc_id, self.config.fallback.neutral_score
                )
                for doc_id in fused_ids
            },
            "lexical_overlap": {
                doc_id: lex_norm.get(doc_id, 0.0) for doc_id in fused_ids
            },
        }
        if ce_norm:
            # Docs outside CE top_m get neutral, not 0 — zeroing them
            # buried recall candidates that never entered the CE window.
            neutral = self.config.fallback.neutral_score
            signals["cross_encoder"] = {
                doc_id: ce_norm.get(doc_id, neutral) for doc_id in fused_ids
            }

        final = weighted_fusion(signals, fusion_weights)
        # Near-copy / rare-token gates on the fused score so CE/RRF cannot
        # resurrect query duplicates (corpus-independent).
        for doc_id in list(final):
            cmeta = chunk_meta.get(doc_id) or {}
            dmeta = doc_fields.get(doc_id) or {}
            title = str(dmeta.get("title") or "")
            body = str(
                cmeta.get("best_chunk_text")
                or " ".join(
                    str(x) for x in (dmeta.get("content") or []) if x
                )
                or ""
            )
            factor = rare_token_multiplier(query, title=title, body=body)
            if self.config.final_fusion.near_copy_penalty:
                factor *= near_copy_penalty(
                    query, f"{title} {body}".strip()
                )
            final[doc_id] = float(final[doc_id]) * factor
        ordered = sorted(
            final, key=final.get, reverse=True  # type: ignore[arg-type]
        )[:return_k]

        hits: list[DualHit] = []
        for doc_id in ordered:
            meta = doc_fields.get(doc_id) or chunk_meta.get(doc_id) or {}
            cmeta = chunk_meta.get(doc_id) or {}
            hits.append(
                DualHit(
                    source_doc_id=doc_id,
                    score=float(final.get(doc_id, 0.0)),
                    scores={
                        name: float(mapping.get(doc_id, 0.0))
                        for name, mapping in signals.items()
                    },
                    title=str(meta.get("title") or ""),
                    json_ld=str(meta.get("json_ld") or ""),
                    best_chunk_text=str(cmeta.get("best_chunk_text") or ""),
                    chunk_id=str(cmeta.get("chunk_id") or ""),
                )
            )

        return DualSearchResult(
            hits=hits,
            expansion=expansion,
            timings_ms=timings,
            active_signals=sorted(active),
            degraded=sorted(set(degraded)),
        )

    async def _search_chunks(
        self,
        expansion: QueryExpansionResult,
        user_space: str,
        q_chunk_emb: list[float] | None,
        q_question_emb: list[float] | None,
        *,
        bm25_projection: str | None = None,
        ranking_profile: str | None = None,
    ) -> tuple[list[str], dict[str, dict[str, Any]]]:
        hits = self.config.retrieval.chunk.hits
        profile = ranking_profile or self.config.retrieval.chunk.profile
        # Prefer compact distinctive projection over raw expansion join.
        # Keep ontology synonym/related terms for surface-form recall.
        probe = (bm25_projection or "").strip()
        if not probe:
            terms = [term.text for term in expansion.terms if term.text]
            probe = " ".join(terms[:12])
        else:
            extra: list[str] = []
            seen = {tok.lower() for tok in probe.split()}
            for term in expansion.terms:
                if term.relation not in (
                    "synonyms",
                    "narrower",
                    "related",
                    "broader",
                ):
                    continue
                tok = (term.text or "").strip()
                if not tok or tok.lower() in seen or len(tok) < 3:
                    continue
                seen.add(tok.lower())
                extra.append(tok)
            if extra:
                probe = f"{probe} {' '.join(extra[:8])}".strip()
        text_clause = ""
        if probe:
            text_clause = build_text_raw_contains_or_clause(probe)
        parts: list[str] = []
        dim = self.vespa.config.embedding_dim
        if q_chunk_emb and len(q_chunk_emb) == dim:
            parts.append(
                f'([{{"targetNumHits": {hits}}}]nearestNeighbor('
                f"chunk_embedding, q_chunk_emb))"
            )
        if q_question_emb and len(q_question_emb) == dim:
            parts.append(
                f'([{{"targetNumHits": {hits}}}]nearestNeighbor('
                f"questions_embeddings, q_question_emb))"
            )
        if text_clause:
            parts.append(text_clause)
        if not parts:
            return [], {}
        yql = "select * from chunk where " + " or ".join(parts)
        timeout_s = max(1, int(self.vespa.config.timeout_seconds))
        payload: dict[str, Any] = {
            "yql": yql,
            "hits": hits,
            "ranking.profile": profile,
            "streaming.groupname": user_space,
            "timeout": f"{timeout_s}s",
        }
        if q_chunk_emb and len(q_chunk_emb) == dim:
            payload["input.query(q_chunk_emb)"] = q_chunk_emb
        if q_question_emb and len(q_question_emb) == dim:
            payload["input.query(q_question_emb)"] = q_question_emb
        LOGGER.debug("chunk YQL profile=%s: %s", profile, yql)
        try:
            response = await self.vespa.search(payload)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Chunk arm failed: %s", exc)
            return [], {}
        children = (response.get("root") or {}).get("children") or []
        # Map to parent source_doc_id; keep best chunk rank per parent.
        best_rank: dict[str, int] = {}
        meta: dict[str, dict[str, Any]] = {}
        for rank, child in enumerate(children, start=1):
            fields = child.get("fields") or {}
            doc_ref = str(fields.get("doc_ref") or "")
            parent_id = str(
                fields.get("source_doc_id")
                or _parent_id_from_doc_ref(doc_ref)
                or fields.get("chunk_id")
                or f"chunk-{rank}"
            )
            if parent_id in best_rank:
                continue
            best_rank[parent_id] = rank
            meta[parent_id] = {
                "doc_ref": doc_ref,
                "chunk_id": fields.get("chunk_id"),
                "best_chunk_text": fields.get("text_raw") or "",
                "source_doc_id": parent_id,
                "relevance": child.get("relevance"),
            }
        ordered = sorted(best_rank, key=best_rank.get)  # type: ignore[arg-type]
        return ordered, meta

    async def _search_documents(
        self,
        expansion: QueryExpansionResult,
        user_space: str,
        normalizer: TextNormalizer | None,
        language: str | None = None,
        *,
        bm25_projection: str | None = None,
    ) -> tuple[list[str], dict[str, dict[str, Any]]]:
        hits = self.config.retrieval.document.hits
        projection = (bm25_projection or "").strip()
        if projection:
            raw_terms = projection.split()[:16]
            # Ontology expansions still matter when surface forms diverge.
            seen = {tok.lower() for tok in raw_terms}
            for term in expansion.terms:
                if term.relation not in (
                    "synonyms",
                    "narrower",
                    "related",
                    "broader",
                ):
                    continue
                tok = (term.text or "").strip()
                if not tok or tok.lower() in seen or len(tok) < 3:
                    continue
                seen.add(tok.lower())
                raw_terms.append(tok)
            raw_terms = raw_terms[:16]
        else:
            raw_terms = [term.text for term in expansion.terms if term.text][:16]
        # Prefer pre-normalized expansion terms (same TextNormalizer as index).
        if projection and normalizer is not None:
            norm_terms = normalize_query_texts(
                raw_terms,
                language=language,
                normalizer=normalizer,
            )
        else:
            norm_terms = [
                term.normalized_text
                for term in expansion.terms
                if term.normalized_text
            ][:16]
            if not norm_terms and normalizer is not None and raw_terms:
                norm_terms = normalize_query_texts(
                    raw_terms[:16],
                    language=language,
                    normalizer=normalizer,
                )
            elif (
                not norm_terms
                and expansion.normalized_query
                and expansion.normalized_query != expansion.raw_query
            ):
                norm_terms = [expansion.normalized_query]

        clauses: list[str] = []
        if raw_terms:
            raw_clause = build_multi_field_contains_or_clause(
                raw_terms[:12],
                fields=("title", "content"),
            )
            if raw_clause:
                clauses.append(raw_clause)
        if norm_terms:
            lem_clause = build_multi_field_contains_or_clause(
                norm_terms[:12],
                fields=("title_lemmatized", "content_lemmatized"),
            )
            if lem_clause:
                clauses.append(lem_clause)
        if not clauses:
            # Fallback: compact projection or truncated raw query on title
            lit = escape_yql_literal(
                projection or expansion.raw_query[:180]
            )
            clauses.append(f'title contains "{lit}"')
        yql = "select * from tkeir_document where " + " or ".join(
            f"({clause})" for clause in clauses
        )
        timeout_s = max(1, int(self.vespa.config.timeout_seconds))
        payload = {
            "yql": yql,
            "hits": hits,
            "ranking.profile": self.config.retrieval.document.profile,
            "streaming.groupname": user_space,
            "timeout": f"{timeout_s}s",
        }
        LOGGER.debug(
            "document YQL (normalized_terms=%d): %s", len(norm_terms), yql
        )
        try:
            response = await self.vespa.search(payload)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Document arm failed: %s", exc)
            return [], {}
        children = (response.get("root") or {}).get("children") or []
        ordered: list[str] = []
        meta: dict[str, dict[str, Any]] = {}
        for child in children:
            fields = child.get("fields") or {}
            doc_id = str(fields.get("source_doc_id") or "")
            if not doc_id or doc_id in meta:
                continue
            ordered.append(doc_id)
            meta[doc_id] = {
                "title": fields.get("title") or "",
                "json_ld": fields.get("json_ld") or "",
                "source_doc_id": doc_id,
                "content": fields.get("content") or [],
                "relevance": child.get("relevance"),
            }
        return ordered, meta


class _IdentityNormalizer:
    """Fallback when spaCy is unavailable."""

    def normalize(self, text: str) -> str:
        return (text or "").lower().strip()


def _parent_id_from_doc_ref(doc_ref: str) -> str | None:
    """Best-effort extract of the id key from a Vespa document reference.

    Prefer ``source_doc_id`` on chunk fields when available; this helper is a
    fallback for older indexes that only store ``doc_ref``.
    """
    if not doc_ref:
        return None
    if ":" in doc_ref:
        return doc_ref.rsplit(":", 1)[-1]
    return doc_ref


def dual_hits_to_vespa_response(hits: list[DualHit]) -> dict[str, Any]:
    """Adapt dual-pipeline hits to a Vespa-like search response for the API."""
    children = []
    for hit in hits:
        children.append(
            {
                "relevance": hit.score,
                "fields": {
                    "chunk_id": hit.chunk_id or hit.source_doc_id,
                    "text_raw": hit.best_chunk_text,
                    "source_doc_id": hit.source_doc_id,
                    "title": hit.title,
                    "json_ld": hit.json_ld,
                    "doc_ref": "",
                },
            }
        )
    return {"root": {"children": children}}
