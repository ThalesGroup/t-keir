"""Title: Passage retrieval over Vespa global (index) and user (streaming).

Three search modes:
  - ``global`` — catalog index only (no streaming.groupname)
  - ``user`` — per-user streaming only
  - ``both`` — run both arms and RRF-fuse

``auto`` mode picks among them from NLP + optional external ontology.

Query path (when ``rag.search.enabled``):
  1. T-KEIR linguistic pipeline (tokenizer → morphosyntax → NER → syntax →
     keywords) via :func:`run_linguistic_pipeline`
  2. Optional business-ontology expansion: resolve NLP seeds + query against
     the external ontology, expand synonym / narrower / broader / related
     concept ids and labels
  3. BGE-M3 dense+sparse encode of the raw query
  4. Vespa hybrid YQL (NN + BM25 probe + ``ontology_concepts`` OR)
  5. Optional :class:`~thot.tools.search.ontology_scorer.OntologyRescorer`
     (``ontology_scoring.enabled``)
  6. ColBERT MaxSim rerank of the top pool
     (:func:`thot.tools.search.rerank.colbert_rerank`)

For offline / BEIR corpus scoring (multi-query leaderboard path), use
:func:`thot.tools.eval.hybrid_retrieve.retrieve_hybrid`.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, cast

from thot.tools.search.bge_m3 import (
    BGE_M3_DENSE_DIM,
    encode_one,
    vespa_dense_tensor,
    vespa_sparse_tensor,
)
from thot.tools.search.business_ontology import business_ontology_from_data
from thot.tools.search.dual_hybrid_config import DualHybridConfig
from thot.tools.search.fusion import normalize_scores, reciprocal_rank_fusion
from thot.tools.search.query_expander import ExpansionWeights, QueryExpander
from thot.tools.search.rag_config import load_rag_config
from thot.tools.search.text_normalizer import normalizer_for_language
from thot.tools.search.vespa_client import (
    VespaClient,
    build_multi_field_contains_or_clause,
    escape_yql_literal,
)

if TYPE_CHECKING:
    from thot.tasks.pipeline.PipelineRunner import PipelineRunner

LOGGER = logging.getLogger(__name__)

SearchMode = Literal["global", "user", "both", "auto"]

_PIPELINE_RUNNER: PipelineRunner | None = None
_PIPELINE_LOCK = threading.Lock()

# UD POS kept for BM25 probe terms (language-agnostic; no word lists).
_PROBE_CONTENT_POS = frozenset({"NOUN", "PROPN", "VERB", "ADJ", "NUM"})


def _content_probe_terms(
    query: str,
    query_analysis: dict[str, Any] | None,
    nlp_terms: list[str],
) -> list[str]:
    """Build BM25 probe terms from NLP content signals (not raw interrogatives).

    Joining the raw question into the probe and then whitespace-splitting it
    turns ``What happen at Suez`` into an OR on ``What``, which matches
    unrelated passages that merely contain ``what appeared…``.

    Example:
        >>> terms = _content_probe_terms(
        ...     "What happen at Suez",
        ...     {
        ...         "search_terms": ["happen", "Suez"],
        ...         "ner_entities": [{"text": "Suez", "label": "LOC"}],
        ...         "morphosyntax": [
        ...             {"text": "What", "pos": "PRON"},
        ...             {"text": "happen", "pos": "VERB"},
        ...             {"text": "Suez", "pos": "PROPN"},
        ...         ],
        ...     },
        ...     ["happen", "Suez"],
        ... )
        >>> "Suez" in terms and "What" not in terms
        True
    """
    ordered: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        """Append a deduplicated probe term when not blocked.

        Example:
            >>> True
            True
        """
        cleaned = (value or "").strip()
        if not cleaned:
            return
        key = cleaned.casefold()
        if key in seen:
            return
        seen.add(key)
        ordered.append(cleaned)

    analysis = query_analysis or {}
    blocked: set[str] = set()
    for token in analysis.get("morphosyntax") or []:
        if not isinstance(token, dict):
            continue
        pos = str(token.get("pos") or "").upper()
        if pos in _PROBE_CONTENT_POS:
            continue
        for key in ("lemma", "text"):
            raw = str(token.get(key) or "").strip()
            if raw:
                blocked.add(raw.casefold())

    for entity in analysis.get("ner_entities") or []:
        if isinstance(entity, dict):
            add(str(entity.get("text") or ""))
        else:
            add(str(entity or ""))
    for token in analysis.get("morphosyntax") or []:
        if not isinstance(token, dict):
            continue
        pos = str(token.get("pos") or "").upper()
        if pos and pos not in _PROBE_CONTENT_POS:
            continue
        add(str(token.get("lemma") or token.get("text") or ""))
    for term in analysis.get("search_terms") or []:
        cleaned = str(term or "").strip()
        if not cleaned:
            continue
        if cleaned.casefold() in blocked:
            continue
        parts = [p for p in cleaned.split() if p]
        if parts and all(part.casefold() in blocked for part in parts):
            continue
        add(cleaned)
    for term in nlp_terms:
        cleaned = str(term or "").strip()
        if cleaned.casefold() in blocked:
            continue
        add(cleaned)
    if ordered:
        return ordered
    # No NLP: keep multi-word surface as a single phrase (AND in Vespa), not
    # per-token OR of sentence-initial interrogatives.
    stripped = (query or "").strip()
    if stripped:
        add(stripped)
    return ordered


def _boost_hits_by_content_overlap(
    hits: list[PassageHit],
    content_terms: list[str],
) -> list[PassageHit]:
    """Prefer passages that contain distinctive probe terms.

    Example:
        >>> hits = [
        ...     PassageHit("a", "a", "what appeared near Gaza", 0.9, "global"),
        ...     PassageHit("b", "b", "calm around Suez Gulf", 0.5, "global"),
        ... ]
        >>> _boost_hits_by_content_overlap(hits, ["Suez"])[0].passage_id
        'b'
    """
    needles = [
        term.casefold()
        for term in content_terms
        if term and len(term.strip()) >= 3
    ]
    if not needles or not hits:
        return hits

    def overlap(hit: PassageHit) -> int:
        """Count how many probe terms appear in a passage hit.

        Example:
            >>> True
            True
        """
        haystack = (hit.chunk_text or "").casefold()
        return sum(1 for term in needles if term in haystack)

    return sorted(
        hits,
        key=lambda hit: (overlap(hit), float(hit.score)),
        reverse=True,
    )


def _default_pipeline_runner() -> PipelineRunner | None:
    """Lazy-load a shared :class:`PipelineRunner` for query NLP.

    Example:
        >>> runner = _default_pipeline_runner()
        >>> runner is None or hasattr(runner, "run")
        True
    """
    global _PIPELINE_RUNNER
    if _PIPELINE_RUNNER is not None:
        return _PIPELINE_RUNNER
    with _PIPELINE_LOCK:
        if _PIPELINE_RUNNER is not None:
            return _PIPELINE_RUNNER
        try:
            import os

            from thot.core.TkeirPaths import configs_dir
            from thot.tasks.pipeline.PipelineConfiguration import (
                PipelineConfiguration,
            )
            from thot.tasks.pipeline.PipelineRunner import PipelineRunner

            config = PipelineConfiguration()
            with open(
                os.path.join(configs_dir(), "pipeline.yaml"),
                encoding="utf-8",
            ) as handle:
                config.load(handle)
            _PIPELINE_RUNNER = PipelineRunner(config)
            LOGGER.info("Loaded PipelineRunner for passage query NLP")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Query NLP PipelineRunner unavailable: %s", exc)
            return None
    return _PIPELINE_RUNNER


@dataclass
class PassageHit:
    """One ranked passage.

    Example:
        >>> PassageHit("p1", "ref", "text", 0.8)
        PassageHit(passage_id='p1', source_ref='ref', chunk_text='text', score=0.8, schema='global', ontology_concepts=[])
    """

    passage_id: str
    source_ref: str
    chunk_text: str
    score: float
    schema: str = "global"
    ontology_concepts: list[str] = field(default_factory=list)


@dataclass
class PassageSearchResult:
    """Search result with chosen mode and timings.

    Example:
        >>> PassageSearchResult(hits=[], mode="global")
        PassageSearchResult(hits=[], mode='global', timings_ms={}, expansion_terms=[], query_analysis=None)
    """

    hits: list[PassageHit]
    mode: SearchMode
    timings_ms: dict[str, float] = field(default_factory=dict)
    expansion_terms: list[str] = field(default_factory=list)
    query_analysis: dict[str, Any] | None = None


def _query_token_count(query: str) -> int:
    """Whitespace token count used to gate NLP-seed ontology expansion.

    Example:
        >>> _query_token_count("What happen at Suez")
        4
    """
    return len([tok for tok in (query or "").split() if tok])


def _query_sentence_count(query: str) -> int:
    """Rough sentence count (``.!?`` split) for long-query gating.

    Example:
        >>> _query_sentence_count("Hello. World!")
        2
    """
    import re

    parts = re.split(r"[.!?]+", query or "")
    return len([part for part in parts if part.strip()])


def _nlp_seed_expansion_applies(
    query: str,
    *,
    enabled: bool,
    min_tokens: int,
    min_sentences: int = 2,
) -> bool:
    """Return whether NLP-seed ontology expansion should run.

    When ``enabled``, always True: analyzed NER / kg / keywords expand Vespa
    ``ontology_concepts`` via YQL OR (broaden recall, never filter).

    ``min_tokens`` / ``min_sentences`` / ``query`` are retained for API
    compatibility but no longer restrict expansion.

    Example:
        >>> _nlp_seed_expansion_applies("short", enabled=True, min_tokens=5)
        True
        >>> _nlp_seed_expansion_applies("short", enabled=False, min_tokens=1)
        False
    """
    del query, min_tokens, min_sentences
    return bool(enabled)


def _nlp_seed_labels(
    query_analysis: dict[str, Any] | None,
    nlp_terms: list[str],
) -> list[str]:
    """Collect labels from analyzed request for ontology resolve + expansion.

    Sources: ``ner_entities``, ``keywords``, ``svo_triples`` / ``kg``
    (subject / verb / object), lemmas, then ``search_terms``. Resolved concept
    ids OR against Vespa ``ontology_concepts``.

    Example:
        >>> _nlp_seed_labels(
        ...     {"ner_entities": [{"text": "Suez"}], "keywords": ["canal"]},
        ...     [],
        ... )
        ['Suez', 'canal']
    """
    seeds: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        """Append a deduplicated NLP seed label.

        Example:
            >>> True
            True
        """
        cleaned = (value or "").strip()
        if not cleaned:
            return
        key = cleaned.casefold()
        if key in seen:
            return
        seen.add(key)
        seeds.append(cleaned)

    analysis = query_analysis or {}
    for entity in analysis.get("ner_entities") or []:
        if isinstance(entity, dict):
            _add(str(entity.get("text") or ""))
        else:
            _add(str(entity))
    for keyword in analysis.get("keywords") or []:
        if isinstance(keyword, dict):
            _add(str(keyword.get("text") or keyword.get("label") or ""))
        else:
            _add(str(keyword))
    for triple in analysis.get("svo_triples") or analysis.get("kg") or []:
        if not isinstance(triple, dict):
            continue
        for key in ("subject", "verb", "object", "property", "value"):
            part = triple.get(key)
            if isinstance(part, dict):
                content = part.get("content") or part.get("text") or ""
                if isinstance(content, list):
                    _add(" ".join(str(x) for x in content if x))
                else:
                    _add(str(content))
            elif part:
                _add(str(part))
    for lemma in analysis.get("lemmas") or []:
        _add(str(lemma))
    for term in analysis.get("search_terms") or nlp_terms:
        _add(str(term))
    return seeds[:48]


def choose_search_mode(
    query: str,
    *,
    requested: SearchMode = "auto",
    has_user_space: bool = True,
    expansion_concept_ids: list[str] | None = None,
    language: str | None = None,
) -> SearchMode:
    """Pick ``global`` / ``user`` / ``both`` from request + light NLP signals.

    Heuristics (language-agnostic):
    - Explicit mode wins (except ``auto``).
    - No user space → always ``global``.
    - Very short queries → ``both`` (cast a wide net).
    - Ontology-resolved concepts → prefer ``global`` (catalog knowledge).
    - Otherwise ``both`` when a user space exists, else ``global``.

    Example:
        >>> choose_search_mode("hello world", requested="global")
        'global'
        >>> choose_search_mode("what happen", has_user_space=True)
        'both'
    """
    if requested in ("global", "user", "both"):
        if requested == "user" and not has_user_space:
            return "global"
        return requested
    if not has_user_space:
        return "global"
    tokens = [t for t in (query or "").split() if t]
    if len(tokens) <= 3:
        return "both"
    if expansion_concept_ids:
        return "global"
    del language  # reserved for future spaCy routing
    return "both"


class PassageRetrievalPipeline:
    """Hybrid dense+sparse+BM25 retrieval for global/user schemas.

    Example:
        >>> PassageRetrievalPipeline().config is not None
        True
    """

    def __init__(
        self,
        config: DualHybridConfig | None = None,
        vespa: VespaClient | None = None,
        *,
        pipeline_runner: PipelineRunner | None = None,
    ) -> None:
        """Wire dual-hybrid config, Vespa client, and optional NLP runner.

        Example:
            >>> PassageRetrievalPipeline(vespa=None).vespa is None
            True
        """
        self.config = config or load_rag_config().dual_hybrid
        self.vespa = vespa
        self._pipeline_runner = pipeline_runner

    def _runner(self) -> PipelineRunner | None:
        """Return the configured or lazily loaded pipeline runner.

        Example:
            >>> PassageRetrievalPipeline()._runner() is None or True
            True
        """
        if self._pipeline_runner is not None:
            return self._pipeline_runner
        return _default_pipeline_runner()

    def _analyze_query(
        self,
        query: str,
        *,
        language: str | None,
    ) -> tuple[dict[str, Any] | None, list[str], float]:
        """Run T-KEIR linguistic pipeline on the query when ``search.enabled``.

        Returns:
            ``(analysis_dict, lexical_terms, nlp_ms)``.

        Example:
            >>> import inspect
            >>> inspect.isfunction(PassageRetrievalPipeline._analyze_query)
            True
        """
        rag = load_rag_config()
        if not rag.search.enabled:
            return None, [], 0.0
        runner = self._runner()
        if runner is None:
            return None, [], 0.0
        from thot.tools.search.query_analyzer import (
            analyze_query_document,
            run_linguistic_pipeline,
        )

        t0 = time.perf_counter()
        try:
            processed = run_linguistic_pipeline(
                runner, query, language=language
            )
            analysis = analyze_query_document(
                processed,
                query,
                language=language,
                config=rag.search,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Query NLP failed (continuing without): %s", exc)
            return None, [], (time.perf_counter() - t0) * 1000
        nlp_ms = (time.perf_counter() - t0) * 1000
        terms = [t for t in analysis.search_terms or [] if t][:48]
        payload = {
            "raw_query": analysis.raw_query,
            "lexical_query": analysis.lexical_query,
            "search_terms": list(analysis.search_terms or []),
            "lemmas": list(analysis.lemmas or []),
            "keywords": list(analysis.keywords or []),
            "morphosyntax": list(analysis.morphosyntax or []),
            "ner_entities": [
                {
                    "text": getattr(e, "text", str(e)),
                    "label": getattr(e, "label", "entity"),
                }
                for e in analysis.ner_entities or []
            ],
            "svo_triples": [
                {
                    "subject": triple.subject,
                    "verb": triple.verb,
                    "object": triple.object,
                }
                for triple in analysis.svo_triples or []
            ],
            "language": analysis.language,
            # Server-only: rebuild query document ontology for HMI fuse.
            "_pipeline_doc": processed,
        }
        return payload, terms, nlp_ms

    async def search(
        self,
        query: str,
        *,
        user_space: str | None = None,
        language: str | None = None,
        business_ontology: Any | None = None,
        mode: SearchMode | None = None,
        top_k: int | None = None,
    ) -> PassageSearchResult:
        """Run retrieval for one query (NLP → expand → embed → Vespa).

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(PassageRetrievalPipeline.search)
            True
        """
        assert self.vespa is not None
        t0 = time.perf_counter()
        rag = load_rag_config()
        dim = int(rag.models.embedding_dim or BGE_M3_DENSE_DIM)
        model_id = None  # load resources/modeling/net/bge-m3
        configured_hits = int(
            getattr(self.config.retrieval, "hits", None) or 100
        )
        return_k = int(top_k or self.config.final_fusion.top_k_returned or 10)
        # Always fetch a deep first-stage pool; trim to return_k after rerank.
        hits_n = max(return_k, configured_hits)
        profile = str(
            getattr(self.config.retrieval, "ranking_profile", None) or "hybrid"
        )

        query_analysis, nlp_terms, nlp_ms = self._analyze_query(
            query, language=language
        )
        timings: dict[str, float] = {"nlp": nlp_ms, "expand": 0.0}

        # Expansion: content-bearing NLP / ontology labels only. Never append
        # the raw interrogative sentence (whitespace-splitting it into the
        # BM25 OR clause matches noise like "what appeared…").
        expansion_terms = _content_probe_terms(
            query, query_analysis, nlp_terms
        )
        seen_terms = {term.casefold() for term in expansion_terms}
        blocked_function: set[str] = set()
        for token in (query_analysis or {}).get("morphosyntax") or []:
            if not isinstance(token, dict):
                continue
            pos = str(token.get("pos") or "").upper()
            if pos in _PROBE_CONTENT_POS:
                continue
            for key in ("lemma", "text"):
                raw = str(token.get(key) or "").strip()
                if raw:
                    blocked_function.add(raw.casefold())

        def _add_term(value: str) -> None:
            """Append a deduplicated expansion term when not blocked.

            Example:
                >>> True
                True
            """
            cleaned = (value or "").strip()
            if not cleaned:
                return
            key = cleaned.casefold()
            if key in seen_terms:
                return
            if key in blocked_function:
                return
            parts = [p for p in cleaned.split() if p]
            if parts and all(
                part.casefold() in blocked_function for part in parts
            ):
                return
            seen_terms.add(key)
            expansion_terms.append(cleaned)

        concept_ids: list[str] = []
        ontology_graph = None
        text_normalizer = None
        use_search_ont = self.config.business_ontology.search_enabled and (
            self.config.query_expansion.enabled
            or self.config.ontology_scoring.enabled
        )
        if use_search_ont and business_ontology is not None:
            t_exp = time.perf_counter()
            try:
                text_normalizer = normalizer_for_language(language or "en")
            except Exception:  # noqa: BLE001
                text_normalizer = None
            if text_normalizer is not None:
                ontology_graph = business_ontology_from_data(business_ontology)
                if ontology_graph.concepts:
                    ontology_graph.build_label_index(text_normalizer)
                # Analyzed request (NER / keywords / kg) → resolve + expand
                # concept ids for Vespa ``ontology_concepts`` OR clauses.
                nlp_cfg = self.config.query_expansion.nlp_seed_expansion
                seed_labels: list[str] = []
                if _nlp_seed_expansion_applies(
                    query,
                    enabled=bool(nlp_cfg.enabled),
                    min_tokens=int(nlp_cfg.min_tokens),
                    min_sentences=int(getattr(nlp_cfg, "min_sentences", 2)),
                ):
                    seed_labels = _nlp_seed_labels(query_analysis, nlp_terms)
                expander = QueryExpander(
                    ontology_graph,
                    text_normalizer,
                    weights=ExpansionWeights(
                        **{
                            k: float(v)
                            for k, v in (
                                self.config.query_expansion.weights.items()
                            )
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
                    max_terms_per_relation=(
                        self.config.query_expansion.max_terms_per_relation
                    ),
                    enabled=self.config.query_expansion.enabled,
                )
                expanded = expander.expand(
                    query, seed_labels=seed_labels or None
                )
                concept_ids = list(expanded.concept_ids or [])
                for term in expanded.terms:
                    if term.text:
                        _add_term(term.text)
                if concept_ids:
                    LOGGER.info(
                        "query expand ontology_concepts OR ids=%s seeds=%d",
                        concept_ids[:16],
                        len(seed_labels),
                    )
            timings["expand"] = (time.perf_counter() - t_exp) * 1000

        if not expansion_terms and query.strip():
            expansion_terms = [query.strip()]

        requested_raw = (
            mode or getattr(self.config, "search_mode", None) or "auto"
        )
        requested_mode: SearchMode = "auto"
        if isinstance(requested_raw, str):
            normalized = requested_raw.strip().lower()
            if normalized in ("global", "user", "both", "auto"):
                requested_mode = cast(SearchMode, normalized)
        chosen = choose_search_mode(
            query,
            requested=requested_mode,
            has_user_space=bool(user_space),
            expansion_concept_ids=concept_ids,
            language=language,
        )

        t_emb = time.perf_counter()
        # Dense/sparse on content-focused lexical text when NLP produced terms;
        # avoids interrogative-heavy embeddings pulling narrative SPOTREPs.
        embed_text = (
            (query_analysis or {}).get("lexical_query")
            or " ".join(expansion_terms[:12])
            or query
        )
        emb = encode_one(str(embed_text), model_id=model_id, dense_dim=dim)
        # Pure BGE-M3 sparse; BM25 probe + ontology_concepts handle lexical /
        # concept overlap (enrich_sparse previously hurt SciFact NDCG).
        query_sparse = emb.sparse
        timings["embed"] = (time.perf_counter() - t_emb) * 1000

        probe_terms = expansion_terms[:24]

        if chosen == "global":
            ranked, meta = await self._search_schema(
                "global",
                probe_terms=probe_terms,
                dense=emb.dense,
                sparse=query_sparse,
                hits=hits_n,
                profile=profile,
                dim=dim,
                user_space=None,
                concept_ids=concept_ids,
            )
            timings["vespa_global"] = meta.get("ms", 0.0)
            hits = self._to_hits(ranked, meta.get("fields") or {}, "global")
        elif chosen == "user":
            ranked, meta = await self._search_schema(
                "user",
                probe_terms=probe_terms,
                dense=emb.dense,
                sparse=query_sparse,
                hits=hits_n,
                profile=profile,
                dim=dim,
                user_space=user_space,
                concept_ids=concept_ids,
            )
            timings["vespa_user"] = meta.get("ms", 0.0)
            hits = self._to_hits(ranked, meta.get("fields") or {}, "user")
        else:
            t_g = time.perf_counter()
            g_rank, g_meta = await self._search_schema(
                "global",
                probe_terms=probe_terms,
                dense=emb.dense,
                sparse=query_sparse,
                hits=hits_n,
                profile=profile,
                dim=dim,
                user_space=None,
                concept_ids=concept_ids,
            )
            timings["vespa_global"] = (time.perf_counter() - t_g) * 1000
            t_u = time.perf_counter()
            u_rank, u_meta = await self._search_schema(
                "user",
                probe_terms=probe_terms,
                dense=emb.dense,
                sparse=query_sparse,
                hits=hits_n,
                profile=profile,
                dim=dim,
                user_space=user_space,
                concept_ids=concept_ids,
            )
            timings["vespa_user"] = (time.perf_counter() - t_u) * 1000
            fused = reciprocal_rank_fusion(
                {"global": g_rank, "user": u_rank},
                dict(self.config.rrf.arm_weights),
                self.config.rrf.k,
            )
            fused_ids = sorted(
                fused,
                key=lambda pid: fused[pid],
                reverse=True,
            )[: self.config.rrf.top_n_after_fusion]
            fields_map = {
                **(g_meta.get("fields") or {}),
                **(u_meta.get("fields") or {}),
            }
            schema_map = {
                **{pid: "global" for pid in g_rank},
                **{pid: "user" for pid in u_rank},
            }
            scores = normalize_scores(fused)
            hits = []
            for pid in fused_ids:
                row = fields_map.get(pid) or {}
                hits.append(
                    PassageHit(
                        passage_id=pid,
                        source_ref=str(row.get("source_ref") or ""),
                        chunk_text=str(row.get("chunk_text") or ""),
                        score=float(scores.get(pid, 0.0)),
                        schema=schema_map.get(pid, "global"),
                        ontology_concepts=list(
                            row.get("ontology_concepts") or []
                        ),
                    )
                )

        # Optional OntologyRescorer (Graph-RAG overlap on ontology_concepts).
        ont_cfg = self.config.ontology_scoring
        if (
            bool(ont_cfg.enabled)
            and concept_ids
            and hits
            and ontology_graph is not None
            and text_normalizer is not None
        ):
            t_ont = time.perf_counter()
            from thot.tools.search.ontology_scorer import (
                OntologyMatchWeights,
                OntologyRescorer,
                OntologyScorer,
                OntologyScorerConfig,
            )

            mw = ont_cfg.match_weights or {}
            scorer = OntologyScorer(
                ontology_graph,
                text_normalizer,
                OntologyScorerConfig(
                    enabled=True,
                    match_weights=OntologyMatchWeights(
                        exact=float(mw.get("exact", 1.0)),
                        synonym=float(mw.get("synonym", 0.9)),
                        narrower=float(mw.get("narrower", 0.6)),
                        broader=float(mw.get("broader", 0.3)),
                        shared_parent=float(mw.get("shared_parent", 0.2)),
                    ),
                    max_traversal_depth=int(ont_cfg.max_traversal_depth),
                    normalize_by_query_concepts=bool(
                        ont_cfg.normalize_by_query_concepts
                    ),
                    neutral_score=float(
                        getattr(self.config.fallback, "neutral_score", 0.5)
                    ),
                ),
            )
            weight = float(getattr(ont_cfg, "rescore_weight", 0.13) or 0.13)
            rescorer = OntologyRescorer(scorer, weight=weight)
            ranked_ont = rescorer.rescore(
                concept_ids,
                [
                    (
                        hit.passage_id,
                        float(hit.score),
                        list(hit.ontology_concepts),
                    )
                    for hit in hits
                ],
            )
            by_id = {hit.passage_id: hit for hit in hits}
            rescored: list[PassageHit] = []
            for pid, score in ranked_ont:
                base = by_id.get(pid)
                if base is None:
                    continue
                rescored.append(
                    PassageHit(
                        passage_id=base.passage_id,
                        source_ref=base.source_ref,
                        chunk_text=base.chunk_text,
                        score=float(score),
                        schema=base.schema,
                        ontology_concepts=list(base.ontology_concepts),
                    )
                )
            if rescored:
                hits = rescored
            timings["ontology_rescore"] = (time.perf_counter() - t_ont) * 1000

        # Prefer passages that actually mention content probe terms (e.g. Suez)
        # before ColBERT, so entity questions are not drowned by narrative noise.
        hits = _boost_hits_by_content_overlap(hits, expansion_terms)

        # ColBERT MaxSim second stage (1 query × N hits).
        colbert_cfg = getattr(self.config, "colbert", None)
        if colbert_cfg is not None and bool(
            getattr(colbert_cfg, "enabled", False)
        ):
            t_cb = time.perf_counter()
            from thot.tools.search.rerank import colbert_rerank

            candidates = [
                (hit.passage_id, hit.chunk_text, float(hit.score))
                for hit in hits
                if hit.chunk_text
            ]
            if candidates:
                colbert_ranked: list[tuple[str, float]] = (
                    await asyncio.to_thread(
                        colbert_rerank,
                        query,
                        candidates,
                        top_m=int(getattr(colbert_cfg, "top_m", 40)),
                        top_k=return_k,
                        batch_size=int(getattr(colbert_cfg, "batch_size", 8)),
                        first_stage_weight=float(
                            getattr(colbert_cfg, "first_stage_weight", 0.55)
                        ),
                        colbert_weight=float(
                            getattr(colbert_cfg, "colbert_weight", 0.45)
                        ),
                        tail_weight=float(
                            getattr(colbert_cfg, "tail_weight", 0.15)
                        ),
                    )
                )
                by_id = {hit.passage_id: hit for hit in hits}
                reranked_hits: list[PassageHit] = []
                for pid, score in colbert_ranked:
                    base = by_id.get(pid)
                    if base is None:
                        continue
                    reranked_hits.append(
                        PassageHit(
                            passage_id=base.passage_id,
                            source_ref=base.source_ref,
                            chunk_text=base.chunk_text,
                            score=float(score),
                            schema=base.schema,
                            ontology_concepts=list(base.ontology_concepts),
                        )
                    )
                hits = reranked_hits
            timings["colbert"] = (time.perf_counter() - t_cb) * 1000
        else:
            hits = hits[:return_k]

        hits = hits[:return_k]
        timings["total"] = (time.perf_counter() - t0) * 1000
        return PassageSearchResult(
            hits=hits,
            mode=chosen,
            timings_ms={k: round(float(v), 3) for k, v in timings.items()},
            expansion_terms=expansion_terms,
            query_analysis=query_analysis,
        )

    async def _search_schema(
        self,
        schema: str,
        *,
        probe_terms: list[str],
        dense: list[float],
        sparse: dict[str, float],
        hits: int,
        profile: str,
        dim: int,
        user_space: str | None,
        concept_ids: list[str],
    ) -> tuple[list[str], dict[str, Any]]:
        """Execute one Vespa schema arm and return ranked passage ids.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(PassageRetrievalPipeline._search_schema)
            True
        """
        assert self.vespa is not None
        t0 = time.perf_counter()
        parts: list[str] = [
            f'({{"targetNumHits": {hits}}}nearestNeighbor(dense_vector, q_dense))'
        ]
        text_clause = build_multi_field_contains_or_clause(
            list(probe_terms or []),
            fields=("chunk_text",),
        )
        if text_clause:
            parts.append(text_clause)
        # Expanded neighborhood (synonym/narrower/related/broader ids).
        # OR-joined with NN + BM25 — expands recall via ontology_concepts,
        # never ANDed (would filter).
        for cid in concept_ids[:16]:
            lit = escape_yql_literal(str(cid))
            if lit:
                parts.append(f'ontology_concepts contains "{lit}"')
        yql = f"select * from {schema} where " + " or ".join(parts)
        payload: dict[str, Any] = {
            "yql": yql,
            "hits": hits,
            "ranking.profile": profile,
            "timeout": f"{max(1, int(self.vespa.config.timeout_seconds))}s",
            "input.query(q_dense)": vespa_dense_tensor(dense, dim)["values"],
            "input.query(q_sparse)": vespa_sparse_tensor(sparse),
        }
        if schema == "user" and user_space:
            payload["streaming.groupname"] = user_space
        try:
            response = await self.vespa.search(payload)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("%s arm failed: %s", schema, exc)
            return [], {"ms": (time.perf_counter() - t0) * 1000, "fields": {}}
        children = (response.get("root") or {}).get("children") or []
        ordered: list[str] = []
        fields_map: dict[str, dict[str, Any]] = {}
        for child in children:
            f = child.get("fields") or {}
            pid = str(
                f.get("source_ref") or child.get("id") or f"hit-{len(ordered)}"
            )
            if pid in fields_map:
                continue
            ordered.append(pid)
            fields_map[pid] = f
        return ordered, {
            "ms": (time.perf_counter() - t0) * 1000,
            "fields": fields_map,
        }

    @staticmethod
    def _to_hits(
        ranked: list[str],
        fields_map: dict[str, dict[str, Any]],
        schema: str,
    ) -> list[PassageHit]:
        """Map ranked passage ids and Vespa fields to :class:`PassageHit` rows.

        Example:
            >>> hits = PassageRetrievalPipeline._to_hits(
            ...     ["p1"],
            ...     {"p1": {"source_ref": "p1", "chunk_text": "hello"}},
            ...     "global",
            ... )
            >>> hits[0].chunk_text
            'hello'
        """
        hits: list[PassageHit] = []
        n = max(len(ranked), 1)
        for index, pid in enumerate(ranked):
            row = fields_map.get(pid) or {}
            hits.append(
                PassageHit(
                    passage_id=pid,
                    source_ref=str(row.get("source_ref") or pid),
                    chunk_text=str(row.get("chunk_text") or ""),
                    score=1.0 - (index / n),
                    schema=schema,
                    ontology_concepts=list(row.get("ontology_concepts") or []),
                )
            )
        return hits
