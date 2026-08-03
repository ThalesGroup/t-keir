"""Title: BEIR smoke evaluation (dev, <5 min)

Fast development harness: for each BEIR corpus (scifact, fiqa, arguana, scidocs)
isolate a tiny index — gold docs for a few selected queries plus noise —
measure BM25 vs T-KEIR dual-hybrid timing/quality, flag rank failures, then
wipe Vespa.

By default, query selection prefers hard failures documented in
``docs/evaluation_report.md`` (override with ``--no-focus-eval-report`` or
``--query-ids``).

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
from thot.tools.eval.beir_eval import (
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

# Hard failures from docs/evaluation_report.md (T-KEIR error analysis when
# available; FiQA uses baseline FP/FN/near-miss ids after T-KEIR was interrupted).
# Order: false positives / false negatives first, then near misses.
EVAL_REPORT_FOCUS_QUERIES: dict[str, tuple[str, ...]] = {
    "scifact": (
        "1",
        "3",
        "5",
        "13",
        "36",
        "127",
        "133",
        "183",
    ),
    "fiqa": (
        "8",
        "15",
        "18",
        "26",
        "34",
        "42",
        "89",
        "104",
        "549",
        "585",
    ),
    # ArguAna / SciDocs not yet covered in the latest evaluation_report.md.
    "arguana": (),
    "scidocs": (),
}

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
    # Concepts loaded from datasets/<name>/business_ontology.yaml (0 if missing).
    ontology_concepts: int = 0
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
    focused_queries: list[str] = field(default_factory=list)


# Map alert codes → (severity, where to look when improving the code).
_ALERT_FOCUS: dict[str, tuple[str, str]] = {
    "tkeir_error": (
        "high",
        "Check Vespa (`make bootstrap`), `beir_tkeir.py` indexing, "
        "and `passage_retrieval.py` search.",
    ),
    "tkeir_ndcg_zero": (
        "high",
        "Likely empty hybrid runs — inspect "
        "`thot.tools.eval.hybrid_retrieve.retrieve_hybrid` and "
        "BGE-M3 / BM25 inputs.",
    ),
    "empty_retrievals": (
        "high",
        "Empty `retrieve_hybrid` results — check corpus texts and "
        "`configs/rag.yaml` (`dual_hybrid.colbert`).",
    ),
    "gold_miss_all": (
        "high",
        "Recall failure on a tiny gold+noise set — inspect "
        "`hybrid_retrieve.py` / `rerank.colbert_rerank` knobs and "
        "embedding quality.",
    ),
    "tkeir_behind_bm25": (
        "medium",
        "Hybrid underperforms BM25 — tune `dual_hybrid.colbert` / "
        "passage hybrid weights in `configs/rag.yaml`.",
    ),
    "slow_index": (
        "medium",
        "Indexing dominates — for speed-only loops use `--index-mode fast`; "
        "for ranking eval keep `chunking` and profile "
        "`index_beir_corpus` / `LlmWrapper.embed_batch`.",
    ),
    "slow_retrieve": (
        "medium",
        "Per-query retrieve is slow — see passage retrieval stage breakdown "
        "in `passage_retrieval.py`.",
    ),
    "slow_stage_colbert": (
        "medium",
        "ColBERT MaxSim dominates — lower "
        "`dual_hybrid.colbert.top_m` / `batch_size` in `configs/rag.yaml`.",
    ),
    "slow_stage_vespa_arms": (
        "medium",
        "Vespa arms dominate — check sequential queries in "
        "`passage_retrieval.py` and rank profiles in "
        "`vespa/vespa_app/schemas/*.sd`.",
    ),
    "slow_stage_lexical": (
        "low",
        "Lexical/normalize cost — `query_expander.py` / "
        "`text_normalizer.py` on large candidate sets; reduce "
        "`rrf.top_n_after_fusion`.",
    ),
    "slow_stage_expand": (
        "low",
        "Expand/normalize slow — `query_expander.py`, "
        "`text_normalizer.py`, ontology payload size.",
    ),
    "slow_stage_rrf": (
        "low",
        "RRF cost unusual — check `fusion.py` / `rrf.top_n_after_fusion`.",
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
    "colbert": 1_500.0,
    "rerank": 1_500.0,
    "vespa_arms": 1_000.0,
    "vespa_chunk": 700.0,
    "vespa_document": 700.0,
    "expand": 400.0,
    "nlp": 400.0,
    "rrf": 200.0,
    "ontology": 400.0,
    "lexical": 200.0,
}


def _fmt_ms(value: float) -> str:
    """Format milliseconds (or seconds when large) for smoke reports.

    Example:
        >>> _fmt_ms(500)
        '500ms'
        >>> _fmt_ms(1500)
        '1.5s'
    """
    sign = "-" if value < 0 else ""
    magnitude = abs(value)
    if magnitude >= 1000:
        return f"{sign}{magnitude / 1000:.1f}s"
    return f"{sign}{magnitude:.0f}ms"


def _truncate(text: str, limit: int = 160) -> str:
    """Collapse whitespace and truncate for report excerpts.

    Example:
        >>> _truncate("a" * 200, 10)
        'aaaaaaaaa…'
    """
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _severity_rank(severity: str) -> int:
    """Return sort key for alert severity (lower = more urgent).

    Example:
        >>> _severity_rank("high") < _severity_rank("low")
        True
    """
    return {"high": 0, "medium": 1, "low": 2}.get(severity, 9)


def _alert(
    code: str,
    detail: str,
    *,
    severity: str | None = None,
    focus: str | None = None,
) -> RankAlert:
    """Build a RankAlert with default severity/focus from ``_ALERT_FOCUS``.

    Example:
        >>> alert = _alert("tkeir_error", "boom")
        >>> alert.code
        'tkeir_error'
        >>> alert.severity
        'high'
    """
    default_sev, default_focus = _ALERT_FOCUS.get(code, ("medium", ""))
    return RankAlert(
        code=code,
        detail=detail,
        severity=severity or default_sev,
        focus=focus if focus is not None else default_focus,
    )


def _doc_text(doc: dict[str, str]) -> str:
    """Join title and body for lexical similarity scoring.

    Example:
        >>> _doc_text({"title": "T", "text": "body"})
        'T body'
    """
    title = (doc.get("title") or "").strip()
    body = (doc.get("text") or "").strip()
    if title and body:
        return f"{title} {body}"
    return title or body


def _token_set(text: str) -> set[str]:
    """Return lowercase alphanumeric tokens from ``text``.

    Example:
        >>> sorted(_token_set("The Cat Sat"))
        ['cat', 'sat', 'the']
    """
    return {tok.lower() for tok in _TOKEN_RE.findall(text or "")}


def _jaccard(left: set[str], right: set[str]) -> float:
    """Compute Jaccard similarity between two token sets.

    Example:
        >>> _jaccard({"cat", "sat"}, {"cat", "mat"})
        0.3333333333333333
    """
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
    """Return up to ``n`` non-excluded docs closest to ``query_text`` (Jaccard).

    Example:
        >>> corpus = {
        ...     "d1": {"text": "cat sat mat"},
        ...     "d2": {"text": "dog ran"},
        ... }
        >>> pick_close_docs("cat mat", corpus, exclude=set(), n=1)
        ['d1']
    """
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


def resolve_focus_query_ids(
    dataset: str,
    *,
    focus_eval_report: bool = True,
    query_ids: list[str] | None = None,
) -> list[str]:
    """Return preferred smoke query ids (CLI override or eval-report focus).

    Example:
        >>> resolve_focus_query_ids("scifact", query_ids=["1", "3"])
        ['1', '3']
    """
    if query_ids:
        return [str(qid).strip() for qid in query_ids if str(qid).strip()]
    if not focus_eval_report:
        return []
    key = str(dataset).strip().lower()
    # BEIR download folder may be fiqa-2018; normalize common aliases.
    if key in {"fiqa-2018", "fiqa2018"}:
        key = "fiqa"
    return list(EVAL_REPORT_FOCUS_QUERIES.get(key) or ())


def build_smoke_subset(
    corpus: dict[str, dict[str, str]],
    queries: dict[str, str],
    qrels: dict[str, dict[str, int]],
    *,
    n_queries: int = DEFAULT_QUERIES,
    n_close: int = DEFAULT_CLOSE_DOCS,
    rank_docs: int = DEFAULT_RANK_DOCS,
    seed: int = 42,
    focus_query_ids: list[str] | None = None,
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

    When ``focus_query_ids`` is set (e.g. eval-report failures), those ids are
    selected first (stable order); remaining slots are filled by RNG shuffle.

    Query ids that also appear in the corpus (ArguAna) are never indexed.

    Args:
        corpus: Full BEIR corpus.
        queries: Full query map.
        qrels: Relevance judgments.
        n_queries: How many queries to keep (default 10).
        n_close: Close distractors per query (default 10).
        rank_docs: Minimum documents to rank per query (default 10).
        seed: RNG seed for query sampling.
        focus_query_ids: Optional preferred query ids (eval-report problems).

    Returns:
        ``(subset_corpus, subset_queries, subset_qrels, stats)``.

    Example:
        >>> corpus = {"d1": {"text": "cat sat"}, "d2": {"text": "dog ran"}}
        >>> queries = {"q1": "cat sat"}
        >>> qrels = {"q1": {"d1": 1}}
        >>> sub_c, sub_q, sub_r, stats = build_smoke_subset(
        ...     corpus, queries, qrels, n_queries=1, n_close=0, rank_docs=1, seed=1
        ... )
        >>> stats["gold_docs"]
        1
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
    eligible_set = set(eligible)

    focus = [qid for qid in focus_query_ids or [] if qid in eligible_set]
    missing_focus = [
        qid for qid in focus_query_ids or [] if qid not in eligible_set
    ]
    selected: list[str] = []
    seen: set[str] = set()
    for qid in focus:
        if qid in seen:
            continue
        selected.append(qid)
        seen.add(qid)
        if len(selected) >= n_queries:
            break
    if len(selected) < n_queries:
        remainder = [qid for qid in eligible if qid not in seen]
        rng.shuffle(remainder)
        for qid in remainder:
            selected.append(qid)
            seen.add(qid)
            if len(selected) >= n_queries:
                break

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
    focused_kept = [qid for qid in selected if qid in set(focus)]
    stats = {
        "gold_docs": len(gold_ids - query_ids),
        "close_docs": len(close_ids - gold_ids - query_ids),
        "noise_docs": len(close_ids - gold_ids - query_ids),  # alias
        "selected_queries": list(selected),
        "focus_query_ids": list(focus),
        "focused_selected": focused_kept,
        "focus_missing": missing_focus,
        "rank_docs": rank_docs,
        "close_per_query": n_close,
        "min_pool_per_query": min_pool,
        "per_query_pool_size": {
            qid: len(per_query_pool[qid]) for qid in selected
        },
    }
    return subset_corpus, subset_queries, subset_qrels, stats


def _metric_ndcg10(metrics: Metrics) -> float:
    """Return NDCG@10 from a Metrics object.

    Example:
        >>> _metric_ndcg10(Metrics(ndcg={"NDCG@10": 0.42}))
        0.42
    """
    return float(metrics.ndcg.get("NDCG@10", metrics.get("NDCG@10", 0.0)))


def _metric_recall10(metrics: Metrics) -> float:
    """Return Recall@10 when present.

    Example:
        >>> _metric_recall10(Metrics(recall={"Recall@10": 0.75}))
        0.75
    """
    return float(
        metrics.recall.get("Recall@10", metrics.get("Recall@10", 0.0))
    )


def smoke_report_dir(root: Path | None = None) -> Path:
    """Return ``reports/beir/smoke`` under the repo root.

    Example:
        >>> smoke_report_dir(Path("/tmp/repo")).as_posix()
        '/tmp/repo/reports/beir/smoke'
    """
    base = Path(root) if root is not None else Path(repo_root())
    return base / "reports" / "beir" / "smoke"


def load_previous_smoke_report(
    out_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Load the last smoke ``report.json`` if present.

    Example:
        >>> load_previous_smoke_report(Path("/nonexistent/smoke")) is None
        True
    """
    directory = out_dir or smoke_report_dir()
    path = directory / "report.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning(
            "Could not read previous smoke report %s: %s", path, exc
        )
        return None
    if not isinstance(data, dict) or "runs" not in data:
        return None
    return data


@dataclass
class DatasetDelta:
    """Per-corpus delta vs the previous smoke report."""

    name: str
    prev_ndcg: float | None
    ndcg: float
    ndcg_delta: float | None
    prev_recall: float | None
    recall: float
    recall_delta: float | None
    prev_high_alerts: int | None
    high_alerts: int
    high_alerts_delta: int | None
    prev_retrieve_ms: float | None
    retrieve_ms: float
    retrieve_delta_ms: float | None
    verdict: str  # better | worse | unchanged | new


@dataclass
class SmokeComparison:
    """Aggregate comparison of the current run vs a previous report."""

    overall: str  # better | worse | mixed | unchanged | no_baseline
    summary: str
    datasets: list[DatasetDelta] = field(default_factory=list)
    prev_wall_s: float | None = None
    wall_s: float = 0.0
    wall_delta_s: float | None = None
    mean_ndcg_delta: float | None = None
    high_alerts_delta: int | None = None


_NDCG_EPS = 0.005


def _high_alert_count(alerts: list[Any]) -> int:
    """Count alerts with severity ``high``.

    Example:
        >>> _high_alert_count([RankAlert(code="x", detail="d", severity="high")])
        1
    """
    count = 0
    for alert in alerts or []:
        if isinstance(alert, RankAlert):
            if alert.severity == "high":
                count += 1
        elif isinstance(alert, dict) and alert.get("severity") == "high":
            count += 1
    return count


def _dataset_verdict(
    *,
    ndcg_delta: float | None,
    high_alerts_delta: int | None,
) -> str:
    """Return per-dataset verdict from NDCG and alert deltas.

    Example:
        >>> _dataset_verdict(ndcg_delta=0.01, high_alerts_delta=-1)
        'better'
    """
    if ndcg_delta is None:
        return "new"
    quality = (
        "better"
        if ndcg_delta > _NDCG_EPS
        else "worse" if ndcg_delta < -_NDCG_EPS else "unchanged"
    )
    if high_alerts_delta is None:
        return quality
    if high_alerts_delta < 0 and quality != "worse":
        return "better" if quality == "unchanged" else quality
    if high_alerts_delta > 0 and quality != "better":
        return "worse" if quality == "unchanged" else quality
    return quality


def compare_smoke_to_previous(
    runs: list[SmokeRun],
    *,
    wall_s: float,
    previous: dict[str, Any] | None,
) -> SmokeComparison:
    """Compare current smoke runs to a previous ``report.json`` payload.

    Ranking quality (T-KEIR NDCG@10) is the primary signal; fewer high-severity
    alerts is secondary. Wall clock is reported but does not drive the verdict.

    Example:
        >>> cmp = compare_smoke_to_previous([], wall_s=1.0, previous=None)
        >>> cmp.overall
        'no_baseline'
    """
    if previous is None:
        return SmokeComparison(
            overall="no_baseline",
            summary="No previous report.json — this run becomes the baseline.",
            wall_s=wall_s,
        )

    prev_runs = {
        str(row.get("name")): row
        for row in previous.get("runs") or []
        if isinstance(row, dict) and row.get("name")
    }
    deltas: list[DatasetDelta] = []
    ndcg_deltas: list[float] = []
    high_prev = 0
    high_new = 0

    for run in runs:
        prev = prev_runs.get(run.name)
        ndcg = _metric_ndcg10(run.tkeir)
        recall = _metric_recall10(run.tkeir)
        high = _high_alert_count(run.alerts)
        high_new += high
        retrieve_ms = float(run.timings.retrieve_ms or 0.0)
        if prev is None:
            deltas.append(
                DatasetDelta(
                    name=run.name,
                    prev_ndcg=None,
                    ndcg=ndcg,
                    ndcg_delta=None,
                    prev_recall=None,
                    recall=recall,
                    recall_delta=None,
                    prev_high_alerts=None,
                    high_alerts=high,
                    high_alerts_delta=None,
                    prev_retrieve_ms=None,
                    retrieve_ms=retrieve_ms,
                    retrieve_delta_ms=None,
                    verdict="new",
                )
            )
            continue
        prev_ndcg = float(prev.get("tkeir_ndcg10") or 0.0)
        prev_recall = float(prev.get("tkeir_recall10") or 0.0)
        prev_high = _high_alert_count(prev.get("alerts") or [])
        high_prev += prev_high
        prev_retrieve = float(
            (prev.get("timings") or {}).get("retrieve_ms") or 0.0
        )
        ndcg_delta = ndcg - prev_ndcg
        ndcg_deltas.append(ndcg_delta)
        high_delta = high - prev_high
        deltas.append(
            DatasetDelta(
                name=run.name,
                prev_ndcg=prev_ndcg,
                ndcg=ndcg,
                ndcg_delta=ndcg_delta,
                prev_recall=prev_recall,
                recall=recall,
                recall_delta=recall - prev_recall,
                prev_high_alerts=prev_high,
                high_alerts=high,
                high_alerts_delta=high_delta,
                prev_retrieve_ms=prev_retrieve,
                retrieve_ms=retrieve_ms,
                retrieve_delta_ms=retrieve_ms - prev_retrieve,
                verdict=_dataset_verdict(
                    ndcg_delta=ndcg_delta,
                    high_alerts_delta=high_delta,
                ),
            )
        )

    prev_wall = previous.get("wall_s")
    prev_wall_f = float(prev_wall) if prev_wall is not None else None
    wall_delta = wall_s - prev_wall_f if prev_wall_f is not None else None
    mean_ndcg_delta = (
        sum(ndcg_deltas) / len(ndcg_deltas) if ndcg_deltas else None
    )
    high_alerts_delta = high_new - high_prev if prev_runs else None

    verdicts = {d.verdict for d in deltas if d.verdict != "new"}
    if not verdicts:
        overall = "unchanged"
        summary = "No overlapping datasets with the previous report."
    elif verdicts == {"unchanged"}:
        overall = "unchanged"
        summary = (
            "Quality essentially unchanged vs previous report "
            f"(mean ΔNDCG@10={mean_ndcg_delta:+.3f})."
            if mean_ndcg_delta is not None
            else "Quality essentially unchanged vs previous report."
        )
    elif verdicts <= {"better", "unchanged"}:
        overall = "better"
        summary = (
            f"**Better** than previous report "
            f"(mean ΔNDCG@10={mean_ndcg_delta:+.3f}, "
            f"high alerts {high_prev}→{high_new})."
        )
    elif verdicts <= {"worse", "unchanged"}:
        overall = "worse"
        summary = (
            f"**Worse** than previous report "
            f"(mean ΔNDCG@10={mean_ndcg_delta:+.3f}, "
            f"high alerts {high_prev}→{high_new})."
        )
    else:
        overall = "mixed"
        better_n = sum(1 for d in deltas if d.verdict == "better")
        worse_n = sum(1 for d in deltas if d.verdict == "worse")
        summary = (
            f"**Mixed** vs previous report "
            f"({better_n} better, {worse_n} worse; "
            f"mean ΔNDCG@10={mean_ndcg_delta:+.3f})."
        )

    return SmokeComparison(
        overall=overall,
        summary=summary,
        datasets=deltas,
        prev_wall_s=prev_wall_f,
        wall_s=wall_s,
        wall_delta_s=wall_delta,
        mean_ndcg_delta=mean_ndcg_delta,
        high_alerts_delta=high_alerts_delta,
    )


def render_comparison_section(comparison: SmokeComparison) -> list[str]:
    """Markdown lines for the vs-previous section.

    Example:
        >>> lines = render_comparison_section(
        ...     SmokeComparison(overall="no_baseline", summary="first run")
        ... )
        >>> lines[0]
        '## Vs previous report'
    """
    lines = ["## Vs previous report", ""]
    if comparison.overall == "no_baseline":
        lines.append(comparison.summary)
        lines.append("")
        return lines

    lines.append(comparison.summary)
    lines.append("")
    if (
        comparison.wall_delta_s is not None
        and comparison.prev_wall_s is not None
    ):
        lines.append(
            f"Wall clock: {_fmt_ms(comparison.wall_s * 1000)} "
            f"(prev {_fmt_ms(comparison.prev_wall_s * 1000)}, "
            f"Δ {_fmt_ms(comparison.wall_delta_s * 1000)})"
        )
        lines.append("")
    lines.extend(
        [
            "| Dataset | Verdict | NDCG@10 (prev→new) | Δ | "
            "High alerts (prev→new) | Retrieve Δ |",
            "|---------|---------|--------------------:|----:|"
            "-----------------------:|-----------:|",
        ]
    )
    for row in comparison.datasets:
        if row.ndcg_delta is None:
            ndcg_cell = f"— → {row.ndcg:.3f}"
            delta_cell = "—"
            high_cell = f"— → {row.high_alerts}"
            ret_cell = "—"
        else:
            ndcg_cell = f"{row.prev_ndcg:.3f}→{row.ndcg:.3f}"
            delta_cell = f"{row.ndcg_delta:+.3f}"
            high_cell = f"{row.prev_high_alerts}→{row.high_alerts}"
            ret_cell = (
                _fmt_ms(row.retrieve_delta_ms)
                if row.retrieve_delta_ms is not None
                else "—"
            )
            if (
                row.retrieve_delta_ms is not None
                and row.retrieve_delta_ms > 0
                and not ret_cell.startswith("+")
                and not ret_cell.startswith("-")
            ):
                ret_cell = f"+{ret_cell}"
        lines.append(
            f"| {row.name} | **{row.verdict}** | {ndcg_cell} | "
            f"{delta_cell} | {high_cell} | {ret_cell} |"
        )
    lines.append("")
    return lines


def detect_rank_alerts(
    *,
    bm25: Metrics,
    tkeir: Metrics,
    tkeir_results: dict[str, dict[str, float]],
    qrels: dict[str, dict[str, int]],
    tkeir_error: str | None,
) -> list[RankAlert]:
    """Flag obvious ranking / strategy failures on the smoke subset.

    Example:
        >>> alerts = detect_rank_alerts(
        ...     bm25=Metrics(ndcg={"NDCG@10": 0.5}),
        ...     tkeir=Metrics(),
        ...     tkeir_results={"q1": {}},
        ...     qrels={"q1": {"d1": 1}},
        ...     tkeir_error=None,
        ... )
        >>> any(a.code == "tkeir_ndcg_zero" for a in alerts)
        True
    """
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
    """Flag stages that dominate wall clock on a smoke-sized run.

    Example:
        >>> alerts = detect_timing_alerts(StageTimings(reset_ms=120_000.0))
        >>> any(a.code == "slow_reset" for a in alerts)
        True
    """
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
    """Index (optional Vespa) + score with production ``retrieve_hybrid``.

    Example:
        >>> asyncio.run(_run_tkeir_smoke(  # doctest: +SKIP
        ...     "scifact",
        ...     {"d1": {"text": "test"}},
        ...     {"q1": "test"},
        ...     language="en",
        ...     top_k=5,
        ...     index_mode="fast",
        ...     reindex=False,
        ... ))
    """
    from thot.tools.eval.beir_tkeir import (
        beir_ontology_for_index,
        beir_ontology_for_search,
        index_beir_corpus,
        load_pipeline_runner,
        log_query_progress,
        reset_vespa_for_beir,
    )
    from thot.tools.eval.hybrid_retrieve import retrieve_hybrid
    from thot.tools.search.rag_config import load_rag_config
    from thot.tools.search.vespa_client import VespaClient

    timings = StageTimings(queries=len(queries), docs_indexed=len(corpus))
    t_all = time.perf_counter()

    rag = load_rag_config()
    dual_cfg = rag.dual_hybrid
    ontology_for_index = beir_ontology_for_index(dataset, dual_cfg=dual_cfg)
    ontology_for_search = beir_ontology_for_search(dataset, dual_cfg=dual_cfg)
    if ontology_for_index:
        timings.ontology_concepts = len(
            (ontology_for_index or {}).get("concepts") or []
        )

    # Smoke still exercises ingest → Vespa when available; ranking uses the
    # same hybrid_retrieve stack as BEIR eval (ColBERT via search.rerank).
    if reindex:
        t0 = time.perf_counter()
        try:
            await asyncio.to_thread(reset_vespa_for_beir)
            timings.reset_ms = (time.perf_counter() - t0) * 1000
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Vespa reset skipped for smoke: %s", exc)

    mode = (index_mode or "chunking").strip().lower()
    runner = None
    if mode != "fast":
        LOGGER.info("Loading PipelineRunner for index_mode=%s …", mode)
        try:
            runner = await asyncio.to_thread(load_pipeline_runner)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("PipelineRunner unavailable: %s", exc)
    else:
        LOGGER.warning(
            "index_mode=fast: PipelineRunner skipped (synthetic chunks only)."
        )

    try:
        async with VespaClient() as vespa:
            if await vespa.health():
                t1 = time.perf_counter()
                indexed = await index_beir_corpus(
                    dataset,
                    corpus,
                    vespa=vespa,
                    runner=runner,
                    language=language,
                    index_mode=mode,
                    progress_every=max(5, len(corpus) // 4 or 1),
                    ontology_payload=ontology_for_index,
                )
                timings.index_ms = (time.perf_counter() - t1) * 1000
                timings.docs_indexed = indexed
            else:
                LOGGER.warning(
                    "Vespa not ready — smoke ranking still runs via "
                    "retrieve_hybrid (no index)"
                )
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Vespa index skipped for smoke: %s", exc)

    t2 = time.perf_counter()
    started = t2

    def _progress(index: int, total: int, qid: str) -> None:
        log_query_progress(
            index,
            total,
            dataset=dataset,
            started=started,
            qid=qid,
            every=1,
        )

    LOGGER.info(
        "Smoke retrieve → eval.hybrid_retrieve.retrieve_hybrid top_k=%d "
        "ontology=%s",
        top_k,
        "yes" if ontology_for_search else "no",
    )
    results = await asyncio.to_thread(
        retrieve_hybrid,
        corpus,
        queries,
        top_k=top_k,
        progress=_progress,
        ontology_payload=ontology_for_search,
        language="en",
    )
    timings.retrieve_ms = (time.perf_counter() - t2) * 1000
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
    focus_eval_report: bool = True,
    query_ids: list[str] | None = None,
) -> SmokeRun:
    """Load one BEIR corpus, build subset, score BM25 + T-KEIR, time stages.

    Example:
        >>> evaluate_smoke_dataset(  # doctest: +SKIP
        ...     "scifact",
        ...     Path("datasets"),
        ...     n_queries=1,
        ...     n_close=0,
        ...     rank_docs=1,
        ...     seed=1,
        ...     top_k=5,
        ...     index_mode="fast",
        ...     language="en",
        ...     skip_tkeir=True,
        ...     reindex=False,
        ... )
    """
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
    focus_ids = resolve_focus_query_ids(
        name,
        focus_eval_report=focus_eval_report,
        query_ids=query_ids,
    )
    if focus_ids:
        LOGGER.info(
            "[%s] focusing smoke on eval-report problem queries: %s",
            name,
            ", ".join(focus_ids),
        )
    subset_corpus, subset_queries, subset_qrels, stats = build_smoke_subset(
        corpus,
        queries,
        qrels,
        n_queries=n_queries,
        n_close=n_close,
        rank_docs=rank_docs,
        seed=seed,
        focus_query_ids=focus_ids or None,
    )
    if stats.get("focus_missing"):
        LOGGER.warning(
            "[%s] eval-report focus ids missing from qrels/corpus: %s",
            name,
            ", ".join(stats["focus_missing"]),
        )
    LOGGER.info(
        "[%s] smoke subset queries=%d gold=%d close=%d "
        "min_pool=%s index_docs=%d rank_docs=%d focused=%s",
        name,
        len(subset_queries),
        stats["gold_docs"],
        stats["close_docs"],
        stats.get("min_pool_per_query"),
        len(subset_corpus),
        rank_docs,
        stats.get("focused_selected") or [],
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
        focused_queries=list(stats.get("focused_selected") or []),
    )


def render_smoke_report(
    runs: list[SmokeRun],
    *,
    wall_s: float,
    comparison: SmokeComparison | None = None,
) -> str:
    """Render an action-oriented Markdown smoke report (problems first).

    Example:
        >>> md = render_smoke_report([], wall_s=1.0)
        >>> md.startswith("# BEIR smoke evaluation")
        True
    """
    lines = [
        "# BEIR smoke evaluation (dev)",
        "",
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%SZ')}  ",
        f"Wall clock: **{_fmt_ms(wall_s * 1000)}**  ",
        "",
    ]
    if comparison is not None:
        lines.extend(render_comparison_section(comparison))
    lines.extend(
        [
            "Use this report to **focus code changes**: fix high-severity items "
            "first, then medium bottlenecks. Each alert names the symptom and "
            "where to look in the codebase.",
            "",
            "Query selection prefers hard failures from "
            "`docs/evaluation_report.md` (SciFact T-KEIR FP/FN/near-miss; "
            "FiQA baseline failures when T-KEIR was interrupted).",
            "",
            "## Focus — problems to fix",
            "",
        ]
    )

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
        key=lambda pair: (
            _severity_rank(pair[1].severity),
            pair[0].name,
            pair[1].code,
        )
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
            "| Dataset | Docs | Q | BM25 NDCG@10 | T-KEIR NDCG@10 (vs prev) | "
            "Δ vs BM25 | Index | Retrieve | Alerts |",
            "|---------|-----:|--:|-------------:|-------------------------:|"
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
            if run.tkeir_error
            and not str(run.tkeir_error).startswith("skipped")
            else ""
        )
        note = "err" if err else str(alerts_n)
        vs_prev = ""
        if comparison is not None:
            match = next(
                (d for d in comparison.datasets if d.name == run.name),
                None,
            )
            if match and match.ndcg_delta is not None:
                vs_prev = f" {match.verdict}({match.ndcg_delta:+.3f})"
        lines.append(
            f"| {run.name} | {run.docs_indexed} | {run.queries} | "
            f"{bm25_n:.3f} | {tkeir_n:.3f}{vs_prev} | {delta_s} | "
            f"{_fmt_ms(run.timings.index_ms)} | "
            f"{_fmt_ms(run.timings.retrieve_ms)} | {note} |"
        )
        if run.focused_queries:
            lines.append(
                f"  - eval-report focus queries: "
                f"`{'`, `'.join(run.focused_queries)}`"
            )

    lines.extend(["", "## Timings (bottleneck view)", ""])
    for run in runs:
        stages = run.timings.dual_avg_ms or {}
        if stages:
            ordered = sorted(
                stages.items(), key=lambda kv: kv[1], reverse=True
            )
            top = ", ".join(f"**{k}**={v:.0f}ms" for k, v in ordered[:3])
            rest = ", ".join(f"{k}={v:.0f}" for k, v in ordered[3:])
            stage_line = top + (f" | {rest}" if rest else "")
        else:
            stage_line = "_no dual-hybrid stages_"
        lines.append(
            f"- **{run.name}**: reset={_fmt_ms(run.timings.reset_ms)}, "
            f"index={_fmt_ms(run.timings.index_ms)}, "
            f"retrieve={_fmt_ms(run.timings.retrieve_ms)}, "
            f"ontology_concepts={int(run.timings.ontology_concepts)} "
            f"(per-query avg stages: {stage_line})"
        )
    lines.append("")
    return "\n".join(lines)


def write_smoke_reports(
    runs: list[SmokeRun],
    *,
    wall_s: float,
    comparison: SmokeComparison | None = None,
    previous: dict[str, Any] | None = None,
) -> Path:
    """Write Markdown + JSON under ``reports/beir/smoke/``.

    When a previous ``report.json`` exists it is copied to ``report.prev.json``
    before overwrite so the next run can still compare.

    Example:
        >>> import inspect
        >>> inspect.isfunction(write_smoke_reports)
        True
    """
    root = Path(repo_root())
    out_dir = smoke_report_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "report.json"
    if json_path.is_file():
        try:
            (out_dir / "report.prev.json").write_text(
                json_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        except OSError as exc:
            LOGGER.warning("Could not archive previous report: %s", exc)

    if comparison is None:
        comparison = compare_smoke_to_previous(
            runs, wall_s=wall_s, previous=previous
        )
    md = render_smoke_report(runs, wall_s=wall_s, comparison=comparison)
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
    focus.sort(
        key=lambda row: (_severity_rank(row["severity"]), row["dataset"])
    )
    payload = []
    for run in runs:
        payload.append(
            {
                "name": run.name,
                "queries": run.queries,
                "focused_queries": list(run.focused_queries),
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
    comparison_payload = {
        "overall": comparison.overall,
        "summary": comparison.summary,
        "mean_ndcg_delta": comparison.mean_ndcg_delta,
        "high_alerts_delta": comparison.high_alerts_delta,
        "prev_wall_s": comparison.prev_wall_s,
        "wall_s": comparison.wall_s,
        "wall_delta_s": comparison.wall_delta_s,
        "datasets": [asdict(row) for row in comparison.datasets],
    }
    json_path.write_text(
        json.dumps(
            {
                "wall_s": wall_s,
                "comparison": comparison_payload,
                "focus": focus,
                "runs": payload,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return md_path


def cleanup_vespa() -> None:
    """Wipe BEIR Vespa data after the smoke run.

    Example:
        >>> cleanup_vespa()  # doctest: +SKIP
    """
    from thot.tools.eval.beir_tkeir import reset_vespa_for_beir

    LOGGER.warning("Smoke cleanup: wiping Vespa DB")
    reset_vespa_for_beir()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the BEIR smoke harness.

    Example:
        >>> args = parse_args(["--skip-tkeir", "--datasets", "scifact"])
        >>> args.skip_tkeir
        True
    """
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
        help=f"BEIR dataset ids (default: {' '.join(DEFAULT_DATASETS)})",
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
        "--focus-eval-report",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Prefer hard-failure query ids from docs/evaluation_report.md "
            "(default: on). Use --no-focus-eval-report for random sampling."
        ),
    )
    parser.add_argument(
        "--query-ids",
        nargs="+",
        default=None,
        help=(
            "Explicit query ids to smoke (overrides eval-report focus). "
            "Example: --query-ids 1 3 5 13"
        ),
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
    """CLI entry: isolate each corpus, time+score, cleanup.

    Example:
        >>> main(["--skip-tkeir", "--datasets", "missing-dataset"])  # doctest: +SKIP
        1
    """
    args = parse_args(argv)
    setup_logging(args.verbose)
    n_close = (
        int(args.noise) if args.noise is not None else int(args.close_docs)
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
                    focus_eval_report=bool(args.focus_eval_report),
                    query_ids=list(args.query_ids) if args.query_ids else None,
                )
            )
    finally:
        if not args.skip_tkeir and not args.no_cleanup:
            try:
                cleanup_vespa()
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("Vespa cleanup failed: %s", exc)

    wall_s = time.perf_counter() - wall0
    previous = load_previous_smoke_report()
    comparison = compare_smoke_to_previous(
        runs, wall_s=wall_s, previous=previous
    )
    report = write_smoke_reports(
        runs,
        wall_s=wall_s,
        comparison=comparison,
        previous=previous,
    )
    print(render_smoke_report(runs, wall_s=wall_s, comparison=comparison))
    print(f"\nWrote {report}")
    if comparison.overall != "no_baseline":
        LOGGER.info(
            "Smoke vs previous: %s — %s",
            comparison.overall,
            comparison.summary,
        )
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
