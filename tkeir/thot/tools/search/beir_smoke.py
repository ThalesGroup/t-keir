"""Title: BEIR smoke evaluation (dev, <5 min)

Fast development harness: for each BEIR corpus (scifact, fiqa, arguana)
isolate a tiny index — gold docs for a few selected queries plus noise —
measure BM25 vs T-KEIR dual-hybrid timing/quality, flag rank failures, then
wipe Vespa.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from thot.core.TkeirPaths import repo_root
from thot.tools.search.beir_eval import (
    DEFAULT_DATASETS,
    Metrics,
    analyze_failures,
    ensure_dataset,
    evaluate_results,
    load_dataset,
    run_bm25,
    setup_logging,
)

LOGGER = logging.getLogger(__name__)

# Defaults sized for ranking evaluation (all CLI/Make-overridable).
DEFAULT_QUERIES = 10
DEFAULT_CLOSE_DOCS = 10  # hard negatives per query (lexically close)
DEFAULT_RANK_DOCS = 10  # min candidates in the indexed pool per query
DEFAULT_TOP_K = 10
# Use NLP through chunking so lemmatized fields + real chunks exist for ranking.
DEFAULT_INDEX_MODE = "chunking"

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


@dataclass
class StageTimings:
    """Wall-clock timings for one isolated corpus run (milliseconds)."""

    reset_ms: float = 0.0
    index_ms: float = 0.0
    bm25_ms: float = 0.0
    retrieve_ms: float = 0.0
    total_ms: float = 0.0
    queries: int = 0
    docs_indexed: int = 0
    dual_avg_ms: dict[str, float] = field(default_factory=dict)


@dataclass
class RankAlert:
    """Detected ranking / strategy / timing problem with a code-focus hint."""

    code: str
    detail: str
    severity: str = "high"  # high | medium | low
    focus: str = ""


@dataclass
class SmokeRun:
    """One corpus smoke result."""

    name: str
    queries: int
    docs_indexed: int
    gold_docs: int
    close_docs: int
    noise_docs: int = 0  # alias kept for older report consumers
    bm25: Metrics = field(default_factory=Metrics)
    tkeir: Metrics = field(default_factory=Metrics)
    timings: StageTimings = field(default_factory=StageTimings)
    alerts: list[RankAlert] = field(default_factory=list)
    failures: list[Any] = field(default_factory=list)
    tkeir_error: str | None = None
    error: str | None = None


# Map alert codes → (severity, where to look when improving the code).
_ALERT_FOCUS: dict[str, tuple[str, str]] = {
    "tkeir_error": (
        "high",
        "Check Vespa (`make bootstrap`), `beir_tkeir.py` indexing, "
        "and `dual_retrieval.py` search.",
    ),
    "tkeir_ndcg_zero": (
        "high",
        "Likely BEIR id mapping / empty hits — inspect "
        "`beir_tkeir._dual_hits_to_beir`, `parse_beir_doc_id`, and "
        "`source_doc_id` in `index_documents.py`.",
    ),
    "empty_retrievals": (
        "high",
        "Vespa YQL / user_space / schema — check `dual_retrieval.py`, "
        "`vespa_client.py`, `configs/rag.yaml` (`dual_hybrid`, "
        "`vespa.user_space`).",
    ),
    "gold_miss_all": (
        "high",
        "Recall failure on a tiny gold+noise set — inspect "
        "`text_normalizer.py`, RRF weights in `fusion.py` / "
        "`configs/rag.yaml`, and embedding quality.",
    ),
    "tkeir_behind_bm25": (
        "medium",
        "Dual-hybrid underperforms BM25 — tune `dual_hybrid` fusion / "
        "cross-encoder in `configs/rag.yaml`; check `rerank.py` and "
        "`LlmWrapper.rerank`.",
    ),
    "slow_index": (
        "medium",
        "Indexing dominates — for speed-only loops use `--index-mode fast`; "
        "for ranking eval keep `chunking` and profile "
        "`index_beir_corpus` / `LlmWrapper.embed_batch`.",
    ),
    "slow_retrieve": (
        "medium",
        "Per-query retrieve is slow — see dual-hybrid stage breakdown "
        "(`cross_encoder` / `vespa_arms` in `dual_retrieval.py`).",
    ),
    "slow_stage_cross_encoder": (
        "medium",
        "Cross-encoder dominates — lower "
        "`dual_hybrid.cross_encoder.top_m`, smaller "
        "`models.reranker_model`, or try "
        "`search.rerank.strategy: embedding_cosine`.",
    ),
    "slow_stage_vespa_arms": (
        "medium",
        "Vespa arms dominate — check sequential queries in "
        "`dual_retrieval.py` and rank profiles in "
        "`vespa/vespa_app/schemas/*.sd`.",
    ),
    "slow_stage_lexical": (
        "low",
        "Lexical overlap scoring cost — `lexical_signal.py` on large "
        "candidate sets; reduce `rrf.top_n_after_fusion`.",
    ),
    "slow_stage_expand": (
        "low",
        "Expand/normalize slow — `query_expander.py`, "
        "`text_normalizer.py`, ontology payload size.",
    ),
    "slow_stage_rrf": (
        "low",
        "RRF cost unusual — check `fusion.py` / "
        "`rrf.top_n_after_fusion`.",
    ),
    "slow_stage_ontology": (
        "low",
        "Ontology overlap cost — `ontology_scorer.py` and expansion "
        "concept count.",
    ),
    "slow_reset": (
        "low",
        "Vespa wipe/redeploy dominates — expected once per corpus; "
        "run a single `BEIR_DATASETS=…` while iterating.",
    ),
}

_SLOW_RESET_MS = 60_000.0
_SLOW_INDEX_PER_DOC_MS = 2_500.0
_SLOW_RETRIEVE_PER_QUERY_MS = 3_000.0
_SLOW_STAGE_MS = {
    "cross_encoder": 1_500.0,
    "vespa_arms": 1_000.0,
    "expand": 400.0,
    "rrf": 200.0,
    "ontology": 400.0,
    "lexical": 200.0,
}


def _fmt_ms(value: float) -> str:
    if value >= 1000:
        return f"{value / 1000:.1f}s"
    return f"{value:.0f}ms"


def _truncate(text: str, limit: int = 160) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _severity_rank(severity: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(severity, 9)


def _alert(
    code: str,
    detail: str,
    *,
    severity: str | None = None,
    focus: str | None = None,
) -> RankAlert:
    """Build a RankAlert with default severity/focus from ``_ALERT_FOCUS``."""
    default_sev, default_focus = _ALERT_FOCUS.get(code, ("medium", ""))
    return RankAlert(
        code=code,
        detail=detail,
        severity=severity or default_sev,
        focus=focus if focus is not None else default_focus,
    )


def _doc_text(doc: dict[str, str]) -> str:
    title = (doc.get("title") or "").strip()
    body = (doc.get("text") or "").strip()
    if title and body:
        return f"{title} {body}"
    return title or body


def _token_set(text: str) -> set[str]:
    return {tok.lower() for tok in _TOKEN_RE.findall(text or "")}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def pick_close_docs(
    query_text: str,
    corpus: dict[str, dict[str, str]],
    *,
    exclude: set[str],
    n: int,
) -> list[str]:
    """Return up to ``n`` non-excluded docs closest to ``query_text`` (Jaccard)."""
    if n <= 0:
        return []
    qtoks = _token_set(query_text)
    scored: list[tuple[float, str]] = []
    for doc_id, doc in corpus.items():
        if doc_id in exclude:
            continue
        score = _jaccard(qtoks, _token_set(_doc_text(doc)))
        scored.append((score, doc_id))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [doc_id for _, doc_id in scored[:n]]


def build_smoke_subset(
    corpus: dict[str, dict[str, str]],
    queries: dict[str, str],
    qrels: dict[str, dict[str, int]],
    *,
    n_queries: int = DEFAULT_QUERIES,
    n_close: int = DEFAULT_CLOSE_DOCS,
    rank_docs: int = DEFAULT_RANK_DOCS,
    seed: int = 42,
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, str],
    dict[str, dict[str, int]],
    dict[str, Any],
]:
    """Build a ranking-focused index: gold + close distractors per query.

    For each selected query the indexed pool includes:
    - all gold documents for that query
    - ``n_close`` lexically closest non-gold documents (hard negatives)
    - additional close docs if needed so the per-query pool has at least
      ``rank_docs`` candidates

    Query ids that also appear in the corpus (ArguAna) are never indexed.

    Args:
        corpus: Full BEIR corpus.
        queries: Full query map.
        qrels: Relevance judgments.
        n_queries: How many queries to keep (default 10).
        n_close: Close distractors per query (default 10).
        rank_docs: Minimum documents to rank per query (default 10).
        seed: RNG seed for query sampling.

    Returns:
        ``(subset_corpus, subset_queries, subset_qrels, stats)``.
    """
    rng = random.Random(seed)
    n_queries = max(1, int(n_queries))
    n_close = max(0, int(n_close))
    rank_docs = max(1, int(rank_docs))

    eligible = [
        qid
        for qid, rels in qrels.items()
        if qid in queries
        and any(
            int(score) > 0 and doc_id in corpus and doc_id != qid
            for doc_id, score in rels.items()
        )
    ]
    if not eligible:
        raise ValueError("no queries with in-corpus gold documents")
    rng.shuffle(eligible)
    selected = eligible[: min(n_queries, len(eligible))]

    gold_ids: set[str] = set()
    close_ids: set[str] = set()
    subset_qrels: dict[str, dict[str, int]] = {}
    per_query_pool: dict[str, list[str]] = {}

    for qid in selected:
        kept: dict[str, int] = {}
        for doc_id, score in qrels[qid].items():
            if int(score) <= 0 or doc_id not in corpus or doc_id == qid:
                continue
            kept[doc_id] = int(score)
            gold_ids.add(doc_id)
        if not kept:
            continue
        subset_qrels[qid] = kept

        exclude = set(kept) | {qid} | set(selected)
        need_close = max(n_close, max(0, rank_docs - len(kept)))
        close = pick_close_docs(
            queries[qid],
            corpus,
            exclude=exclude,
            n=need_close,
        )
        close_ids.update(close)
        pool = list(dict.fromkeys([*kept.keys(), *close]))
        # Pad further if corpus still allows (ensure rank_docs candidates).
        if len(pool) < rank_docs:
            more = pick_close_docs(
                queries[qid],
                corpus,
                exclude=exclude | set(pool),
                n=rank_docs - len(pool),
            )
            close_ids.update(more)
            pool.extend(more)
        per_query_pool[qid] = pool

    if not subset_qrels:
        raise ValueError("selected queries have no usable gold documents")

    selected = [qid for qid in selected if qid in subset_qrels]
    query_ids = set(selected)
    indexed_ids = (gold_ids | close_ids) - query_ids
    subset_corpus = {
        doc_id: corpus[doc_id] for doc_id in indexed_ids if doc_id in corpus
    }
    subset_queries = {qid: queries[qid] for qid in selected}
    min_pool = min((len(per_query_pool[qid]) for qid in selected), default=0)
    stats = {
        "gold_docs": len(gold_ids - query_ids),
        "close_docs": len(close_ids - gold_ids - query_ids),
        "noise_docs": len(close_ids - gold_ids - query_ids),  # alias
        "selected_queries": list(selected),
        "rank_docs": rank_docs,
        "close_per_query": n_close,
        "min_pool_per_query": min_pool,
        "per_query_pool_size": {
            qid: len(per_query_pool[qid]) for qid in selected
        },
    }
    return subset_corpus, subset_queries, subset_qrels, stats


def _metric_ndcg10(metrics: Metrics) -> float:
    """Return NDCG@10 from a Metrics object."""
    return float(metrics.ndcg.get("NDCG@10", metrics.get("NDCG@10", 0.0)))


def _metric_recall10(metrics: Metrics) -> float:
    """Return Recall@10 when present."""
    return float(
        metrics.recall.get("Recall@10", metrics.get("Recall@10", 0.0))
    )


def detect_rank_alerts(
    *,
    bm25: Metrics,
    tkeir: Metrics,
    tkeir_results: dict[str, dict[str, float]],
    qrels: dict[str, dict[str, int]],
    tkeir_error: str | None,
) -> list[RankAlert]:
    """Flag obvious ranking / strategy failures on the smoke subset."""
    alerts: list[RankAlert] = []
    if tkeir_error:
        if not str(tkeir_error).startswith("skipped"):
            alerts.append(_alert("tkeir_error", tkeir_error))
        return alerts

    bm25_n = _metric_ndcg10(bm25)
    tkeir_n = _metric_ndcg10(tkeir)
    if tkeir_n <= 0.0 and bm25_n > 0.0:
        alerts.append(
            _alert(
                "tkeir_ndcg_zero",
                f"T-KEIR NDCG@10=0 while BM25={bm25_n:.3f} "
                "(dual-hybrid / mapping failure likely)",
            )
        )
    elif bm25_n > 0.05 and tkeir_n < bm25_n * 0.5:
        alerts.append(
            _alert(
                "tkeir_behind_bm25",
                f"T-KEIR NDCG@10={tkeir_n:.3f} < 50% of BM25={bm25_n:.3f}",
            )
        )

    empty = sum(1 for scores in tkeir_results.values() if not scores)
    if empty:
        alerts.append(
            _alert(
                "empty_retrievals",
                f"{empty}/{len(tkeir_results)} queries returned zero hits",
            )
        )

    miss_all = 0
    for qid, rels in qrels.items():
        gold = {doc_id for doc_id, score in rels.items() if int(score) > 0}
        ranked = set((tkeir_results.get(qid) or {}).keys())
        if gold and not (gold & ranked):
            miss_all += 1
    if miss_all:
        alerts.append(
            _alert(
                "gold_miss_all",
                f"{miss_all}/{len(qrels)} queries missed every gold doc in top-k",
            )
        )
    return alerts


def detect_timing_alerts(timings: StageTimings) -> list[RankAlert]:
    """Flag stages that dominate wall clock on a smoke-sized run."""
    alerts: list[RankAlert] = []
    docs = max(1, timings.docs_indexed)
    queries = max(1, timings.queries)
    if timings.reset_ms >= _SLOW_RESET_MS:
        alerts.append(
            _alert(
                "slow_reset",
                f"Vespa reset took {_fmt_ms(timings.reset_ms)}",
            )
        )
    if timings.index_ms / docs >= _SLOW_INDEX_PER_DOC_MS:
        alerts.append(
            _alert(
                "slow_index",
                f"Index {_fmt_ms(timings.index_ms)} for {docs} docs "
                f"({timings.index_ms / docs:.0f} ms/doc)",
            )
        )
    if timings.retrieve_ms / queries >= _SLOW_RETRIEVE_PER_QUERY_MS:
        alerts.append(
            _alert(
                "slow_retrieve",
                f"Retrieve {_fmt_ms(timings.retrieve_ms)} for {queries} "
                f"queries ({timings.retrieve_ms / queries:.0f} ms/query)",
            )
        )
    for stage, limit in _SLOW_STAGE_MS.items():
        avg = float(timings.dual_avg_ms.get(stage, 0.0))
        if avg >= limit:
            alerts.append(
                _alert(
                    f"slow_stage_{stage}",
                    f"Avg dual-hybrid stage `{stage}` = {avg:.0f} ms/query "
                    f"(threshold {limit:.0f} ms)",
                )
            )
    return alerts


async def _run_tkeir_smoke(
    dataset: str,
    corpus: dict[str, dict[str, str]],
    queries: dict[str, str],
    *,
    language: str,
    top_k: int,
    index_mode: str,
    reindex: bool,
) -> tuple[dict[str, dict[str, float]], StageTimings, str | None]:
    """Index + retrieve one smoke corpus; collect stage timings."""
    from dataclasses import replace

    from thot.core.LlmWrapper import UnifiedLLMWrapper
    from thot.tools.search.beir_tkeir import (
        RetrievalEmbeddingClient,
        _dual_hits_to_beir,
        index_beir_corpus,
        load_beir_business_ontology_payload,
        load_pipeline_runner,
        reset_vespa_for_beir,
    )
    from thot.tools.search.dual_retrieval import DualHybridPipeline
    from thot.tools.search.rag_config import load_rag_config
    from thot.tools.search.vespa_client import VespaClient

    timings = StageTimings(queries=len(queries), docs_indexed=len(corpus))
    t_all = time.perf_counter()

    if reindex:
        t0 = time.perf_counter()
        await asyncio.to_thread(reset_vespa_for_beir)
        timings.reset_ms = (time.perf_counter() - t0) * 1000

    mode = (index_mode or "chunking").strip().lower()
    runner = None
    if mode != "fast":
        LOGGER.info(
            "Loading PipelineRunner for index_mode=%s (NLP through %s)…",
            mode,
            "chunking+chunk-questions" if mode == "full" else "chunking",
        )
        runner = await asyncio.to_thread(load_pipeline_runner)
    else:
        LOGGER.warning(
            "index_mode=fast: PipelineRunner skipped (synthetic chunks only). "
            "Use --index-mode chunking for real NLP ranking eval."
        )

    async with UnifiedLLMWrapper() as llm_full, VespaClient() as vespa:
        llm = RetrievalEmbeddingClient(llm_full)
        await llm.verify_provider(pull_missing=True, include_reranker=True)
        if not await vespa.health():
            raise RuntimeError(
                "Vespa is not ready. Run: make bootstrap"
            )

        t1 = time.perf_counter()
        indexed = await index_beir_corpus(
            dataset,
            corpus,
            vespa=vespa,
            llm=llm,
            runner=runner,
            language=language,
            index_mode=mode,
            progress_every=max(5, len(corpus) // 4 or 1),
        )
        timings.index_ms = (time.perf_counter() - t1) * 1000
        timings.docs_indexed = indexed
        if indexed == 0:
            raise RuntimeError(f"indexed 0/{len(corpus)} docs for {dataset}")

        rag = load_rag_config()
        dual_cfg = rag.dual_hybrid
        # Smoke corpora are tiny: avoid hits=100 + dual NN (streaming 504).
        arm_hits = max(top_k * 2, min(30, max(10, indexed)))
        ce_top_m = max(1, min(top_k, dual_cfg.cross_encoder.top_m, 20))
        from thot.tools.search.dual_hybrid_config import (
            ArmRetrievalConfig,
            DualRetrievalArms,
        )

        dual_cfg = replace(
            dual_cfg,
            enabled=True,
            retrieval=DualRetrievalArms(
                chunk=ArmRetrievalConfig(
                    profile=dual_cfg.retrieval.chunk.profile,
                    hits=arm_hits,
                ),
                document=ArmRetrievalConfig(
                    profile=dual_cfg.retrieval.document.profile,
                    hits=arm_hits,
                ),
            ),
            cross_encoder=replace(
                dual_cfg.cross_encoder, enabled=True, top_m=ce_top_m
            ),
            final_fusion=replace(
                dual_cfg.final_fusion, top_k_returned=max(1, top_k)
            ),
            rrf=replace(
                dual_cfg.rrf,
                top_n_after_fusion=max(top_k, ce_top_m, arm_hits),
            ),
        )
        LOGGER.info(
            "Dual-hybrid smoke retrieve hits=%d ce_top_m=%d top_k=%d",
            arm_hits,
            ce_top_m,
            top_k,
        )
        pipeline = DualHybridPipeline(dual_cfg, vespa, llm=llm)
        ontology_payload = load_beir_business_ontology_payload(dataset)
        if ontology_payload:
            LOGGER.info(
                "Smoke using business ontology for %s (%d concepts)",
                dataset,
                len(ontology_payload.get("concepts") or []),
            )
        space = vespa.config.user_space
        results: dict[str, dict[str, float]] = {}
        stage_sums: dict[str, float] = {}
        stage_n = 0
        t2 = time.perf_counter()
        for qid, qtext in queries.items():
            emb = await llm.embed(qtext)
            dual = await pipeline.search(
                qtext,
                user_space=space,
                language=language,
                q_chunk_emb=emb,
                q_question_emb=emb,
                top_k=top_k,
                business_ontology=ontology_payload,
            )
            results[qid] = _dual_hits_to_beir(dual.hits, dataset)
            for key, value in (dual.timings_ms or {}).items():
                stage_sums[key] = stage_sums.get(key, 0.0) + float(value)
            stage_n += 1
        timings.retrieve_ms = (time.perf_counter() - t2) * 1000
        if stage_n:
            timings.dual_avg_ms = {
                key: value / stage_n for key, value in stage_sums.items()
            }

    timings.total_ms = (time.perf_counter() - t_all) * 1000
    return results, timings, None


def evaluate_smoke_dataset(
    name: str,
    datasets_dir: Path,
    *,
    n_queries: int,
    n_close: int,
    rank_docs: int,
    seed: int,
    top_k: int,
    index_mode: str,
    language: str,
    skip_tkeir: bool,
    reindex: bool,
) -> SmokeRun:
    """Load one BEIR corpus, build subset, score BM25 + T-KEIR, time stages."""
    empty = Metrics()
    path = ensure_dataset(name, datasets_dir)
    if path is None:
        return SmokeRun(
            name=name,
            queries=0,
            docs_indexed=0,
            gold_docs=0,
            close_docs=0,
            error="dataset missing / download failed",
        )

    corpus, queries, qrels = load_dataset(path)
    subset_corpus, subset_queries, subset_qrels, stats = build_smoke_subset(
        corpus,
        queries,
        qrels,
        n_queries=n_queries,
        n_close=n_close,
        rank_docs=rank_docs,
        seed=seed,
    )
    LOGGER.info(
        "[%s] smoke subset queries=%d gold=%d close=%d "
        "min_pool=%s index_docs=%d rank_docs=%d",
        name,
        len(subset_queries),
        stats["gold_docs"],
        stats["close_docs"],
        stats.get("min_pool_per_query"),
        len(subset_corpus),
        rank_docs,
    )

    t_bm25 = time.perf_counter()
    bm25_results = run_bm25(subset_corpus, subset_queries, top_k=top_k)
    bm25_ms = (time.perf_counter() - t_bm25) * 1000
    bm25_metrics = evaluate_results(subset_qrels, bm25_results)

    timings = StageTimings(
        bm25_ms=bm25_ms,
        queries=len(subset_queries),
        docs_indexed=len(subset_corpus),
    )
    tkeir_metrics = empty
    tkeir_results: dict[str, dict[str, float]] = {
        qid: {} for qid in subset_queries
    }
    tkeir_error: str | None = None
    alerts: list[RankAlert] = []
    failures: list[Any] = []

    if skip_tkeir:
        tkeir_error = "skipped (--skip-tkeir)"
    else:
        try:
            tkeir_results, timings, tkeir_error = asyncio.run(
                _run_tkeir_smoke(
                    name,
                    subset_corpus,
                    subset_queries,
                    language=language,
                    top_k=top_k,
                    index_mode=index_mode,
                    reindex=reindex,
                )
            )
            timings.bm25_ms = bm25_ms
            tkeir_metrics = evaluate_results(subset_qrels, tkeir_results)
            failures = analyze_failures(
                subset_queries,
                subset_corpus,
                subset_qrels,
                tkeir_results,
                max_per_kind=2,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("T-KEIR smoke failed on %s", name)
            tkeir_error = str(exc)

    alerts = detect_rank_alerts(
        bm25=bm25_metrics,
        tkeir=tkeir_metrics,
        tkeir_results=tkeir_results,
        qrels=subset_qrels,
        tkeir_error=tkeir_error,
    )
    if not skip_tkeir and not (
        tkeir_error and str(tkeir_error).startswith("skipped")
    ):
        alerts.extend(detect_timing_alerts(timings))
    alerts.sort(key=lambda a: (_severity_rank(a.severity), a.code))
    return SmokeRun(
        name=name,
        queries=len(subset_queries),
        docs_indexed=len(subset_corpus),
        gold_docs=int(stats["gold_docs"]),
        close_docs=int(stats["close_docs"]),
        noise_docs=int(stats["close_docs"]),
        bm25=bm25_metrics,
        tkeir=tkeir_metrics,
        timings=timings,
        alerts=alerts,
        failures=failures,
        tkeir_error=tkeir_error,
    )


def render_smoke_report(runs: list[SmokeRun], *, wall_s: float) -> str:
    """Render an action-oriented Markdown smoke report (problems first)."""
    lines = [
        "# BEIR smoke evaluation (dev)",
        "",
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%SZ')}  ",
        f"Wall clock: **{_fmt_ms(wall_s * 1000)}**  ",
        "",
        "Use this report to **focus code changes**: fix high-severity items "
        "first, then medium bottlenecks. Each alert names the symptom and "
        "where to look in the codebase.",
        "",
        "## Focus — problems to fix",
        "",
    ]

    focus_items: list[tuple[SmokeRun, RankAlert]] = []
    for run in runs:
        for alert in run.alerts:
            focus_items.append((run, alert))
        if run.error:
            focus_items.append(
                (
                    run,
                    _alert("tkeir_error", run.error),
                )
            )
    focus_items.sort(
        key=lambda pair: (_severity_rank(pair[1].severity), pair[0].name, pair[1].code)
    )

    if not focus_items:
        lines.append(
            "No ranking or timing alerts. Smoke subset looks healthy — "
            "proceed to `make beir-eval` for full evidence."
        )
        lines.append("")
    else:
        for index, (run, alert) in enumerate(focus_items, start=1):
            lines.append(
                f"{index}. **[{alert.severity.upper()}] {run.name}** "
                f"`{alert.code}` — {alert.detail}"
            )
            if alert.focus:
                lines.append(f"   - **Code focus:** {alert.focus}")
            lines.append("")

    lines.extend(["## Failure examples (for reproduction)", ""])
    any_failure = False
    for run in runs:
        if not run.failures:
            continue
        any_failure = True
        lines.append(f"### {run.name}")
        lines.append("")
        for case in run.failures:
            kind = getattr(case, "kind", "?")
            qid = getattr(case, "query_id", "?")
            qtext = _truncate(getattr(case, "query_text", ""), 200)
            detail = _truncate(getattr(case, "detail", ""), 240)
            analysis = _truncate(getattr(case, "analysis", ""), 280)
            rank = getattr(case, "rank", None)
            doc_id = getattr(case, "doc_id", None)
            lines.append(f"- **{kind}** query `{qid}`")
            lines.append(f"  - query: {_truncate(qtext, 200)}")
            if doc_id:
                lines.append(
                    f"  - doc `{doc_id}`"
                    + (f" (rank {rank})" if rank is not None else "")
                )
            if detail:
                lines.append(f"  - detail: {detail}")
            if analysis:
                lines.append(f"  - analysis: {analysis}")
        lines.append("")
    if not any_failure:
        lines.append("_No false-positive / false-negative examples captured._")
        lines.append("")

    lines.extend(
        [
            "## Summary metrics",
            "",
            "| Dataset | Docs | Q | BM25 NDCG@10 | T-KEIR NDCG@10 | "
            "Δ vs BM25 | Index | Retrieve | Alerts |",
            "|---------|-----:|--:|-------------:|---------------:|"
            "---------:|-------:|---------:|-------:|",
        ]
    )
    for run in runs:
        bm25_n = _metric_ndcg10(run.bm25)
        tkeir_n = _metric_ndcg10(run.tkeir)
        delta = tkeir_n - bm25_n
        delta_s = f"{delta:+.3f}"
        alerts_n = len(run.alerts)
        err = run.error or (
            run.tkeir_error
            if run.tkeir_error and not str(run.tkeir_error).startswith("skipped")
            else ""
        )
        note = "err" if err else str(alerts_n)
        lines.append(
            f"| {run.name} | {run.docs_indexed} | {run.queries} | "
            f"{bm25_n:.3f} | {tkeir_n:.3f} | {delta_s} | "
            f"{_fmt_ms(run.timings.index_ms)} | "
            f"{_fmt_ms(run.timings.retrieve_ms)} | {note} |"
        )

    lines.extend(["", "## Timings (bottleneck view)", ""])
    for run in runs:
        stages = run.timings.dual_avg_ms or {}
        if stages:
            ordered = sorted(stages.items(), key=lambda kv: kv[1], reverse=True)
            top = ", ".join(f"**{k}**={v:.0f}ms" for k, v in ordered[:3])
            rest = ", ".join(f"{k}={v:.0f}" for k, v in ordered[3:])
            stage_line = top + (f" | {rest}" if rest else "")
        else:
            stage_line = "_no dual-hybrid stages_"
        lines.append(
            f"- **{run.name}**: reset={_fmt_ms(run.timings.reset_ms)}, "
            f"index={_fmt_ms(run.timings.index_ms)}, "
            f"retrieve={_fmt_ms(run.timings.retrieve_ms)} "
            f"(per-query avg stages: {stage_line})"
        )
    lines.append("")
    return "\n".join(lines)


def write_smoke_reports(runs: list[SmokeRun], *, wall_s: float) -> Path:
    """Write Markdown + JSON under ``reports/beir/smoke/``."""
    root = Path(repo_root())
    out_dir = root / "reports" / "beir" / "smoke"
    out_dir.mkdir(parents=True, exist_ok=True)
    md = render_smoke_report(runs, wall_s=wall_s)
    md_path = out_dir / "report.md"
    md_path.write_text(md, encoding="utf-8")
    focus = []
    for run in runs:
        for alert in run.alerts:
            focus.append(
                {
                    "dataset": run.name,
                    "severity": alert.severity,
                    "code": alert.code,
                    "detail": alert.detail,
                    "focus": alert.focus,
                }
            )
        if run.error:
            focus.append(
                {
                    "dataset": run.name,
                    "severity": "high",
                    "code": "tkeir_error",
                    "detail": run.error,
                    "focus": _ALERT_FOCUS["tkeir_error"][1],
                }
            )
    focus.sort(key=lambda row: (_severity_rank(row["severity"]), row["dataset"]))
    payload = []
    for run in runs:
        payload.append(
            {
                "name": run.name,
                "queries": run.queries,
                "docs_indexed": run.docs_indexed,
                "gold_docs": run.gold_docs,
                "close_docs": run.close_docs,
                "noise_docs": run.close_docs,
                "bm25_ndcg10": _metric_ndcg10(run.bm25),
                "tkeir_ndcg10": _metric_ndcg10(run.tkeir),
                "bm25_recall10": _metric_recall10(run.bm25),
                "tkeir_recall10": _metric_recall10(run.tkeir),
                "timings": asdict(run.timings),
                "alerts": [asdict(a) for a in run.alerts],
                "failures": [
                    {
                        "kind": getattr(case, "kind", None),
                        "query_id": getattr(case, "query_id", None),
                        "query_text": getattr(case, "query_text", None),
                        "doc_id": getattr(case, "doc_id", None),
                        "rank": getattr(case, "rank", None),
                        "detail": getattr(case, "detail", None),
                        "analysis": getattr(case, "analysis", None),
                    }
                    for case in run.failures
                ],
                "tkeir_error": run.tkeir_error,
                "error": run.error,
            }
        )
    (out_dir / "report.json").write_text(
        json.dumps(
            {"wall_s": wall_s, "focus": focus, "runs": payload},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return md_path


def cleanup_vespa() -> None:
    """Wipe BEIR Vespa data after the smoke run."""
    from thot.tools.search.beir_tkeir import reset_vespa_for_beir

    LOGGER.warning("Smoke cleanup: wiping Vespa DB")
    reset_vespa_for_beir()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the BEIR smoke harness."""
    parser = argparse.ArgumentParser(
        description=(
            "Fast BEIR smoke eval (<5 min): per query gold + close "
            "distractors, time BM25 vs T-KEIR, flag rank failures, cleanup Vespa"
        )
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=list(DEFAULT_DATASETS),
        help="BEIR dataset ids (default: scifact fiqa arguana)",
    )
    parser.add_argument(
        "--datasets-dir",
        type=Path,
        default=Path("datasets"),
        help="BEIR datasets directory",
    )
    parser.add_argument(
        "--queries",
        type=int,
        default=DEFAULT_QUERIES,
        help=f"Queries per corpus (default: {DEFAULT_QUERIES})",
    )
    parser.add_argument(
        "--close-docs",
        type=int,
        default=DEFAULT_CLOSE_DOCS,
        help=(
            "Lexically close distractors (hard negatives) per query "
            f"(default: {DEFAULT_CLOSE_DOCS})"
        ),
    )
    parser.add_argument(
        "--rank-docs",
        type=int,
        default=DEFAULT_RANK_DOCS,
        help=(
            "Minimum documents in the indexed pool per query "
            f"(default: {DEFAULT_RANK_DOCS})"
        ),
    )
    parser.add_argument(
        "--noise",
        type=int,
        default=None,
        help="Deprecated alias for --close-docs (global pool size ignored)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Subset sampling seed",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Retrieval cutoff / docs scored per query (default: {DEFAULT_TOP_K})",
    )
    parser.add_argument(
        "--index-mode",
        choices=("fast", "chunking", "full"),
        default=DEFAULT_INDEX_MODE,
        help="T-KEIR index depth (default: chunking — runs NLP pipeline)",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Pipeline / normalizer language",
    )
    parser.add_argument(
        "--skip-tkeir",
        action="store_true",
        help="BM25-only smoke (no Vespa)",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Keep Vespa index after the run",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry: isolate each corpus, time+score, cleanup."""
    args = parse_args(argv)
    setup_logging(args.verbose)
    n_close = (
        int(args.noise)
        if args.noise is not None
        else int(args.close_docs)
    )
    rank_docs = max(1, int(args.rank_docs))
    top_k = max(int(args.top_k), rank_docs)
    if top_k != int(args.top_k):
        LOGGER.info(
            "Raising --top-k from %s to %s to match --rank-docs",
            args.top_k,
            top_k,
        )
    wall0 = time.perf_counter()
    runs: list[SmokeRun] = []
    try:
        for name in args.datasets:
            LOGGER.info("========== smoke %s ==========", name)
            runs.append(
                evaluate_smoke_dataset(
                    name,
                    args.datasets_dir,
                    n_queries=max(1, int(args.queries)),
                    n_close=max(0, n_close),
                    rank_docs=rank_docs,
                    seed=args.seed,
                    top_k=top_k,
                    index_mode=args.index_mode,
                    language=args.language,
                    skip_tkeir=args.skip_tkeir,
                    reindex=not args.skip_tkeir,
                )
            )
    finally:
        if not args.skip_tkeir and not args.no_cleanup:
            try:
                cleanup_vespa()
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("Vespa cleanup failed: %s", exc)

    wall_s = time.perf_counter() - wall0
    report = write_smoke_reports(runs, wall_s=wall_s)
    print(render_smoke_report(runs, wall_s=wall_s))
    print(f"\nWrote {report}")
    if wall_s > 300:
        LOGGER.warning(
            "Smoke wall clock %.1fs exceeded 5 min target — "
            "reduce --queries/--close-docs or use --index-mode fast",
            wall_s,
        )
    failed = any(r.error for r in runs) or any(
        a.code == "tkeir_error"
        and not (r.tkeir_error or "").startswith("skipped")
        for r in runs
        for a in r.alerts
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
