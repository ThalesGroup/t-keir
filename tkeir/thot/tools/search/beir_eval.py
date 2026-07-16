# -*- coding: utf-8 -*-
"""BEIR retrieval evaluation: BM25, dense, and T-KEIR pipeline vs leaderboard.

Downloads SciFact, FiQA, and ArguAna when missing under ``./datasets/``, runs
lexical (BM25), dense (SentenceTransformer), and the T-KEIR **retrieval**
stack (NLP index + QueryAnalyzer + Vespa hybrid; **no answer generation**)
at top-100, computes NDCG@10 / MAP@100 / Recall@100, performs error
analysis, and writes ``evaluation_report.md`` with a BEIR leaderboard
comparison.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

BEIR_BASE_URL = (
    "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets"
)
DEFAULT_DATASETS = ("scifact", "fiqa", "arguana")
DEFAULT_DENSE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 100
K_VALUES = [10, 100]
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

# BEIR leaderboard NDCG@10 reference scores (publicly reported baselines).
LEADERBOARD_NDCG10: dict[str, dict[str, float]] = {
    "scifact": {"BM25": 0.665, "SPLADE": 0.699, "Contriever": 0.677},
    "fiqa": {"BM25": 0.236, "SPLADE": 0.342, "Contriever": 0.329},
    "arguana": {"BM25": 0.397, "SPLADE": 0.472, "Contriever": 0.435},
}

DATASET_DISPLAY: dict[str, str] = {
    "scifact": "SciFact",
    "fiqa": "FiQA-2018",
    "arguana": "ArguAna",
}

QUALITATIVE_NOTES: dict[str, str] = {
    "scifact": (
        "SciFact pairs scientific claims with abstract-level evidence. "
        "BM25 often succeeds when claim tokens overlap heavily with abstracts, "
        "but fails on paraphrased claims, negation, and statistical evidence "
        "phrased differently from the gold paper. Dense retrieval recovers some "
        "paraphrases via semantic similarity, yet can still miss when the gold "
        "abstract shares little surface form and the embedding space under-"
        "represents niche biomedical entities."
    ),
    "fiqa": (
        "FiQA questions use specialized financial jargon (tickers, instruments, "
        "accounting terms). Lexical mismatch is the dominant failure mode: "
        "queries mention colloquial investor language while gold posts use "
        "formal or acronym-heavy phrasing. Dense models help when wording "
        "differs but sense is shared; they still struggle with numeral-heavy "
        "or ticker-specific questions where the correct answer document is "
        "short and dominated by symbols rather than natural language."
    ),
    "arguana": (
        "ArguAna is counterargument retrieval: the relevant document is often "
        "an opposing stance that deliberately avoids repeating the query's "
        "key phrases. Pure lexical overlap therefore systematically "
        "under-ranks true counterarguments and promotes thematically similar "
        "but stance-aligned essays (false positives). Dense retrieval mitigates "
        "some lexical gaps, but stance polarity and argumentative structure "
        "are not encoded strongly by generic sentence embeddings, so many "
        "gold counterarguments remain buried outside the top ranks."
    ),
}


@dataclass
class Metrics:
    """Aggregation of standard IR metrics for one retriever on one dataset."""

    ndcg: dict[str, float] = field(default_factory=dict)
    map_: dict[str, float] = field(default_factory=dict)
    recall: dict[str, float] = field(default_factory=dict)
    precision: dict[str, float] = field(default_factory=dict)

    def get(self, name: str, default: float = 0.0) -> float:
        """Return a metric by key looking across stored dicts.

        Args:
            name: Metric key such as ``NDCG@10``.
            default: Value when the key is missing.

        Returns:
            Metric float.

        Example:
            >>> Metrics(ndcg={"NDCG@10": 0.5}).get("NDCG@10")
            0.5
        """
        found = self.lookup(name)
        return default if found is None else found

    def lookup(self, name: str) -> float | None:
        """Return a metric by key, or ``None`` when it was never recorded.

        Args:
            name: Metric key such as ``NDCG@10``.

        Returns:
            Metric float, or ``None`` if absent (e.g. skipped retriever).

        Example:
            >>> Metrics().lookup("NDCG@10") is None
            True
        """
        for bucket in (self.ndcg, self.map_, self.recall, self.precision):
            if name in bucket:
                return float(bucket[name])
        return None


@dataclass
class FailureCase:
    """One qualitative retrieval failure instance."""

    kind: str
    query_id: str
    query_text: str
    detail: str
    score: float | None = None


@dataclass
class DatasetRun:
    """Full evaluation artifact for a single BEIR dataset."""

    name: str
    corpus_size: int
    query_count: int
    bm25: Metrics
    dense: Metrics
    tkeir: Metrics
    failures_bm25: list[FailureCase]
    failures_dense: list[FailureCase]
    failures_tkeir: list[FailureCase]
    dense_model: str
    error: str | None = None
    tkeir_error: str | None = None


def setup_logging(verbose: bool = False) -> None:
    """Configure root logging for the evaluation CLI.

    Args:
        verbose: When True, use DEBUG; otherwise INFO.

    Example:
        >>> setup_logging(False)  # doctest: +SKIP
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokenization for BM25.

    Args:
        text: Raw document or query text.

    Returns:
        Token list (may be empty).

    Example:
        >>> tokenize("Hello, SciFact-42!")
        ['hello', 'scifact', '42']
    """
    return _TOKEN_RE.findall(text.lower())


def document_text(doc: dict[str, str]) -> str:
    """Concatenate BEIR title and text fields for indexing/search.

    Args:
        doc: Corpus entry with optional ``title`` and ``text``.

    Returns:
        Joined string.

    Example:
        >>> document_text({"title": "A", "text": "B"})
        'A B'
    """
    title = (doc.get("title") or "").strip()
    body = (doc.get("text") or "").strip()
    if title and body:
        return f"{title} {body}"
    return title or body


def ensure_dataset(name: str, datasets_dir: Path) -> Path | None:
    """Download and unzip a BEIR dataset if it is not already present.

    Args:
        name: Dataset id (e.g. ``scifact``).
        datasets_dir: Directory that should contain ``{name}/``.

    Returns:
        Path to the dataset folder, or ``None`` if download/load prep failed.

    Example:
        >>> ensure_dataset("scifact", Path("./datasets"))  # doctest: +SKIP
    """
    from beir import util

    target = datasets_dir / name
    marker = target / "corpus.jsonl"
    if marker.is_file():
        LOGGER.info("Dataset '%s' already present at %s", name, target)
        return target

    datasets_dir.mkdir(parents=True, exist_ok=True)
    url = f"{BEIR_BASE_URL}/{name}.zip"
    LOGGER.info("Downloading BEIR dataset '%s' from %s", name, url)
    try:
        data_path = util.download_and_unzip(url, str(datasets_dir))
    except Exception as exc:  # noqa: BLE001 — soft-fail downloads
        LOGGER.error("Failed to download '%s': %s", name, exc)
        return None

    path = Path(data_path)
    if not (path / "corpus.jsonl").is_file():
        # download_and_unzip may return the parent or the dataset folder
        candidate = datasets_dir / name
        if (candidate / "corpus.jsonl").is_file():
            return candidate
        LOGGER.error("Dataset '%s' missing corpus.jsonl after download", name)
        return None
    return path


def load_dataset(
    data_path: Path, split: str = "test"
) -> tuple[
    dict[str, dict[str, str]], dict[str, str], dict[str, dict[str, int]]
]:
    """Load corpus, queries, and qrels via BEIR GenericDataLoader.

    Args:
        data_path: Unzipped dataset directory.
        split: Qrels split name (usually ``test``).

    Returns:
        ``(corpus, queries, qrels)`` dictionaries.

    Example:
        >>> load_dataset(Path("datasets/scifact"))  # doctest: +SKIP
    """
    from beir.datasets.data_loader import GenericDataLoader

    LOGGER.info("Loading dataset from %s (split=%s)", data_path, split)
    corpus, queries, qrels = GenericDataLoader(str(data_path)).load(
        split=split
    )
    LOGGER.info(
        "Loaded %d documents, %d queries, %d qrel queries",
        len(corpus),
        len(queries),
        len(qrels),
    )
    return corpus, queries, qrels


class BM25ExactSearch:
    """In-memory BM25 (Okapi) searcher compatible with BEIR result format.

    Avoids the Elasticsearch dependency used by BEIR's stock ``BM25Search``.
    """

    def __init__(self) -> None:
        """Create an uninitialized BM25 searcher.

        Example:
            >>> searcher = BM25ExactSearch()
            >>> searcher._bm25 is None
            True
        """
        self._bm25: Any = None
        self._doc_ids: list[str] = []

    def index(self, corpus: dict[str, dict[str, str]]) -> None:
        """Build the BM25 index over the corpus.

        Args:
            corpus: Mapping of doc_id → ``{title, text}``.

        Example:
            >>> s = BM25ExactSearch()
            >>> s.index({"d1": {"title": "Cat", "text": "animals"}})
        """
        from rank_bm25 import BM25Okapi

        self._doc_ids = list(corpus.keys())
        tokenized = [
            tokenize(document_text(corpus[did])) for did in self._doc_ids
        ]
        # Ensure no empty token lists (rank_bm25 divides by doc length)
        tokenized = [toks if toks else ["_"] for toks in tokenized]
        self._bm25 = BM25Okapi(tokenized)
        LOGGER.info("BM25 indexed %d documents", len(self._doc_ids))

    def search(
        self,
        corpus: dict[str, dict[str, str]],
        queries: dict[str, str],
        top_k: int,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, dict[str, float]]:
        """Retrieve top-k documents for every query.

        Args:
            corpus: Full corpus (used to (re)build the index if needed).
            queries: Mapping of query_id → query text.
            top_k: Number of hits to keep per query.
            *args: Ignored (BEIR compatibility).
            **kwargs: Ignored (BEIR compatibility).

        Returns:
            Nested dict ``{qid: {doc_id: score}}``.

        Example:
            >>> s = BM25ExactSearch()
            >>> s.search({"d1": {"title": "", "text": "dog"}}, {"q": "dog"}, 1)
            {'q': {'d1': ...}}
        """
        del args, kwargs
        if self._bm25 is None:
            self.index(corpus)
        assert self._bm25 is not None

        results: dict[str, dict[str, float]] = {}
        for qid, qtext in queries.items():
            q_tokens = tokenize(qtext)
            if not q_tokens:
                results[qid] = {}
                continue
            scores = self._bm25.get_scores(q_tokens)
            if top_k >= len(scores):
                ranked_idx = sorted(
                    range(len(scores)), key=lambda i: scores[i], reverse=True
                )
            else:
                # Partial sort for speed on larger corpora
                top_idx = sorted(
                    range(len(scores)), key=lambda i: scores[i], reverse=True
                )[:top_k]
                ranked_idx = top_idx
            hits: dict[str, float] = {}
            for i in ranked_idx[:top_k]:
                score = float(scores[i])
                if not math.isfinite(score):
                    continue
                hits[self._doc_ids[i]] = score
            results[qid] = hits
        return results


def run_bm25(
    corpus: dict[str, dict[str, str]],
    queries: dict[str, str],
    top_k: int = TOP_K,
) -> dict[str, dict[str, float]]:
    """Run BM25 retrieval for all queries.

    Args:
        corpus: BEIR corpus.
        queries: BEIR queries.
        top_k: Cutoff for returned documents.

    Returns:
        BEIR-style results dict.

    Example:
        >>> run_bm25({"d": {"title": "", "text": "x"}}, {"q": "x"}, 1)  # doctest: +SKIP
    """
    from beir.retrieval.evaluation import EvaluateRetrieval

    model = BM25ExactSearch()
    retriever = EvaluateRetrieval(model, k_values=K_VALUES)
    LOGGER.info("Running BM25 retrieval (top_k=%d)…", top_k)
    return retriever.retrieve(corpus, queries)


def run_dense(
    corpus: dict[str, dict[str, str]],
    queries: dict[str, str],
    model_name: str = DEFAULT_DENSE_MODEL,
    batch_size: int = 32,
) -> dict[str, dict[str, float]]:
    """Run dense bi-encoder retrieval with SentenceTransformer embeddings.

    Args:
        corpus: BEIR corpus.
        queries: BEIR queries.
        model_name: HuggingFace / SentenceTransformers model id.
        batch_size: Encode batch size.

    Returns:
        BEIR-style results dict.

    Example:
        >>> run_dense({}, {}, "sentence-transformers/all-MiniLM-L6-v2")  # doctest: +SKIP
    """
    from beir.retrieval import models
    from beir.retrieval.evaluation import EvaluateRetrieval
    from beir.retrieval.search.dense import DenseRetrievalExactSearch as DRES

    LOGGER.info("Loading dense model '%s'…", model_name)
    model = DRES(models.SentenceBERT(model_name), batch_size=batch_size)
    retriever = EvaluateRetrieval(
        model, score_function="cos_sim", k_values=K_VALUES
    )
    LOGGER.info("Running dense retrieval (top_k=%d)…", retriever.top_k)
    return retriever.retrieve(corpus, queries)


def evaluate_results(
    qrels: dict[str, dict[str, int]],
    results: dict[str, dict[str, float]],
) -> Metrics:
    """Compute NDCG / MAP / Recall / Precision via BEIR EvaluateRetrieval.

    Args:
        qrels: Gold relevance judgments.
        results: Retriever scores.

    Returns:
        Populated :class:`Metrics`.

    Example:
        >>> evaluate_results({"q": {"d": 1}}, {"q": {"d": 1.0}})  # doctest: +SKIP
    """
    from beir.retrieval.evaluation import EvaluateRetrieval

    ndcg, map_, recall, precision = EvaluateRetrieval.evaluate(
        qrels, results, K_VALUES
    )
    return Metrics(ndcg=ndcg, map_=map_, recall=recall, precision=precision)


def _truncate(text: str, limit: int = 160) -> str:
    """Collapse whitespace and truncate for report excerpts.

    Args:
        text: Source string.
        limit: Max characters.

    Returns:
        Cleaned short string.

    Example:
        >>> _truncate("a" * 200, 10)
        'aaaaaaaaaa…'
    """
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _first_false_positive(
    qid: str,
    qtext: str,
    ranked: list[tuple[str, float]],
    gold_ids: set[str],
    corpus: dict[str, dict[str, str]],
) -> FailureCase | None:
    """Return the first top-3 irrelevant hit, if any.

    Args:
        qid: Query identifier.
        qtext: Query text.
        ranked: Score-sorted ``(doc_id, score)`` pairs.
        gold_ids: Relevant document ids for the query.
        corpus: Full corpus.

    Returns:
        A false-positive :class:`FailureCase`, or ``None``.

    Example:
        >>> _first_false_positive("q", "x", [("d", 1.0)], {"d"}, {}) is None
        True
    """
    for rank, (did, score) in enumerate(ranked[:3], start=1):
        if did in gold_ids:
            continue
        doc = corpus.get(did, {})
        return FailureCase(
            kind="false_positive",
            query_id=qid,
            query_text=_truncate(qtext),
            detail=(
                f"Rank #{rank} doc `{did}` "
                f"(score={score:.4f}) is not relevant. "
                f"Snippet: {_truncate(document_text(doc), 120)}"
            ),
            score=score,
        )
    return None


def _gold_rank_failures(
    qid: str,
    qtext: str,
    gold_ids: set[str],
    ranked_ids: list[str],
    results: dict[str, dict[str, float]],
    corpus: dict[str, dict[str, str]],
) -> tuple[FailureCase | None, FailureCase | None]:
    """Find one false-negative and one near-miss among gold documents.

    Args:
        qid: Query identifier.
        qtext: Query text.
        gold_ids: Relevant document ids.
        ranked_ids: Retrieved ids ordered by descending score.
        results: Full retriever scores for score lookup.
        corpus: Full corpus.

    Returns:
        ``(false_negative, near_miss)`` — either may be ``None``.

    Example:
        >>> _gold_rank_failures("q", "x", set(), [], {}, {})
        (None, None)
    """
    false_neg: FailureCase | None = None
    near_miss: FailureCase | None = None
    for gdid in gold_ids:
        if gdid not in ranked_ids:
            if false_neg is None:
                false_neg = FailureCase(
                    kind="false_negative",
                    query_id=qid,
                    query_text=_truncate(qtext),
                    detail=(
                        f"Gold doc `{gdid}` completely missed "
                        f"(not in top-{TOP_K}). "
                        f"Snippet: "
                        f"{_truncate(document_text(corpus.get(gdid, {})), 120)}"
                    ),
                )
            continue
        rank = ranked_ids.index(gdid) + 1
        if rank > 10 and near_miss is None:
            near_miss = FailureCase(
                kind="near_miss",
                query_id=qid,
                query_text=_truncate(qtext),
                detail=(
                    f"Gold doc `{gdid}` retrieved at rank "
                    f"{rank}/100 (missed NDCG@10). "
                    f"Snippet: "
                    f"{_truncate(document_text(corpus.get(gdid, {})), 120)}"
                ),
                score=results.get(qid, {}).get(gdid),
            )
        if false_neg is not None and near_miss is not None:
            break
    return false_neg, near_miss


def analyze_failures(
    queries: dict[str, str],
    corpus: dict[str, dict[str, str]],
    qrels: dict[str, dict[str, int]],
    results: dict[str, dict[str, float]],
    max_per_kind: int = 1,
) -> list[FailureCase]:
    """Extract false positives, false negatives, and near-miss failures.

    Failure kinds:
        * **false_positive** — irrelevant doc ranked in the top-3 with a high score
        * **false_negative** — gold doc completely absent from the top-100
        * **near_miss** — gold doc retrieved between ranks 11 and 100

    Args:
        queries: Query id → text.
        corpus: Document id → fields.
        qrels: Gold judgments.
        results: Retriever scores.
        max_per_kind: How many examples to keep per failure type.

    Returns:
        List of up to ``3 * max_per_kind`` failure cases.

    Example:
        >>> analyze_failures({"q": "x"}, {"d": {"title": "", "text": "x"}},
        ...                  {"q": {"d": 1}}, {"q": {"d": 1.0}})
        []
    """
    fps: list[FailureCase] = []
    fns: list[FailureCase] = []
    near: list[FailureCase] = []

    for qid, gold in qrels.items():
        ranked = sorted(
            results.get(qid, {}).items(), key=lambda kv: kv[1], reverse=True
        )
        ranked_ids = [did for did, _ in ranked]
        gold_ids = {did for did, rel in gold.items() if rel > 0}
        qtext = queries.get(qid, "")

        if len(fps) < max_per_kind:
            fp = _first_false_positive(qid, qtext, ranked, gold_ids, corpus)
            if fp is not None:
                fps.append(fp)

        if len(fns) < max_per_kind or len(near) < max_per_kind:
            fn, nm = _gold_rank_failures(
                qid, qtext, gold_ids, ranked_ids, results, corpus
            )
            if fn is not None and len(fns) < max_per_kind:
                fns.append(fn)
            if nm is not None and len(near) < max_per_kind:
                near.append(nm)

        if (
            len(fps) >= max_per_kind
            and len(fns) >= max_per_kind
            and len(near) >= max_per_kind
        ):
            break

    return fps + fns + near


def _fmt(value: float | None, digits: int = 3) -> str:
    """Format a float for Markdown tables.

    Args:
        value: Metric or ``None``.
        digits: Decimal places.

    Returns:
        Formatted string or em-dash.

    Example:
        >>> _fmt(0.665)
        '0.665'
    """
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def _delta(ours: float, baseline: float) -> str:
    """Format signed delta versus a leaderboard baseline.

    Args:
        ours: Our NDCG@10.
        baseline: Reference score.

    Returns:
        Signed delta string.

    Example:
        >>> _delta(0.70, 0.665)
        '+0.035'
    """
    d = ours - baseline
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:.3f}"


def _best_leaderboard(
    board: dict[str, float],
) -> tuple[str, float]:
    """Return the best published BEIR NDCG@10 system and its score.

    Args:
        board: Mapping of system name → NDCG@10.

    Returns:
        ``(system_name, ndcg10)`` for the maximum entry; ``("—", 0.0)`` if empty.

    Example:
        >>> _best_leaderboard({"BM25": 0.6, "SPLADE": 0.7})
        ('SPLADE', 0.7)
    """
    if not board:
        return "—", 0.0
    name = max(board, key=board.get)  # type: ignore[arg-type]
    return name, float(board[name])


def _gap_to_best(score: float | None, best: float) -> str:
    """Format gap of ``score`` relative to the best system (score − best).

    Negative values mean the system trails the leaderboard best.

    Args:
        score: Candidate NDCG@10, or ``None`` when unavailable.
        best: Best published NDCG@10 on the same dataset.

    Returns:
        Signed gap string, or em-dash when ``score`` is missing.

    Example:
        >>> _gap_to_best(0.650, 0.699)
        '-0.049'
    """
    if score is None:
        return "—"
    return _delta(score, best)


def render_report(runs: list[DatasetRun], dense_model: str) -> str:
    """Build the Markdown evaluation report with T-KEIR vs leaderboard.

    Args:
        runs: Per-dataset evaluation results.
        dense_model: Dense embedding model name used in the run.

    Returns:
        Markdown document string.

    Example:
        >>> "# BEIR" in render_report([], "mini")
        True
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "# BEIR Retrieval Evaluation Report",
        "",
        f"_Generated {now}_",
        "",
        "## Overview",
        "",
        "This report benchmarks three retrieval systems on BEIR datasets:",
        "",
        "1. **T-KEIR retrieval only** — full-document NLP indexing + "
        "QueryAnalyzer + adaptive Vespa rank profiles. Answer generation "
        "is **not** run (embeddings only).",
        f"2. **Local BM25 (Okapi)** — in-memory `rank_bm25` baseline.",
        f"3. **Local dense** — SentenceTransformer `{dense_model}`.",
        "",
        f"Retrieval cut-off is **top-{TOP_K}**. Metrics use "
        "`beir.retrieval.evaluation.EvaluateRetrieval` (pytrec_eval).",
        "",
        "> **Leaderboard:** SciFact / FiQA-2018 / ArguAna NDCG@10 values for "
        "BM25, SPLADE, and Contriever are the published BEIR reference "
        "scores. Local BM25 is not Elasticsearch-identical; dense MiniLM is "
        "not Contriever. **T-KEIR** is the system under evaluation against "
        "that public leaderboard.",
        "",
        "## Leaderboard comparison (NDCG@10)",
        "",
        "Gap = system NDCG@10 − **best published** NDCG@10 on that dataset "
        "(among BEIR BM25, SPLADE, Contriever). Negative ⇒ behind the "
        "leaderboard leader.",
        "",
        "| Dataset | Best published | Best score | **T-KEIR** | "
        "Gap T-KEIR → best | Local BM25 | Gap BM25 → best | "
        "Local Dense | Gap Dense → best |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for run in runs:
        board = LEADERBOARD_NDCG10.get(run.name, {})
        best_name, best_score = _best_leaderboard(board)
        label = DATASET_DISPLAY.get(run.name, run.name)
        if run.error:
            lines.append(
                f"| {label} | {best_name} | {_fmt(best_score)} | "
                f"— | — | — | — | — | — |"
            )
            continue
        tkeir_ndcg = None if run.tkeir_error else run.tkeir.lookup("NDCG@10")
        if run.tkeir_error and run.tkeir_error.startswith("skipped"):
            tkeir_cell = "—"
        elif run.tkeir_error:
            tkeir_cell = f"err ({run.tkeir_error[:32]})"
        else:
            tkeir_cell = _fmt(tkeir_ndcg)
        bm25_ndcg = run.bm25.lookup("NDCG@10")
        dense_ndcg = run.dense.lookup("NDCG@10")
        lines.append(
            f"| {label} | {best_name} | {_fmt(best_score)} | "
            f"{tkeir_cell} | {_gap_to_best(tkeir_ndcg, best_score)} | "
            f"{_fmt(bm25_ndcg)} | {_gap_to_best(bm25_ndcg, best_score)} | "
            f"{_fmt(dense_ndcg)} | {_gap_to_best(dense_ndcg, best_score)} |"
        )

    lines.extend(
        [
            "",
            "### Published baselines (reference)",
            "",
            "| Dataset | BEIR BM25 | SPLADE | Contriever | **Best** |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for run in runs:
        board = LEADERBOARD_NDCG10.get(run.name, {})
        best_name, best_score = _best_leaderboard(board)
        label = DATASET_DISPLAY.get(run.name, run.name)
        lines.append(
            f"| {label} | {_fmt(board.get('BM25'))} | "
            f"{_fmt(board.get('SPLADE'))} | "
            f"{_fmt(board.get('Contriever'))} | "
            f"**{best_name}** ({_fmt(best_score)}) |"
        )

    lines.extend(
        [
            "",
            "### Gap to best published system (detail)",
            "",
            "| Dataset | Best system | Best NDCG@10 | T-KEIR gap | "
            "Local BM25 gap | Local Dense gap | T-KEIR vs BM25 | "
            "T-KEIR vs SPLADE | T-KEIR vs Contriever |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for run in runs:
        board = LEADERBOARD_NDCG10.get(run.name, {})
        best_name, best_score = _best_leaderboard(board)
        label = DATASET_DISPLAY.get(run.name, run.name)
        if run.error:
            lines.append(
                f"| {label} | {best_name} | {_fmt(best_score)} | "
                f"— | — | — | — | — | — |"
            )
            continue
        tkeir_ndcg = None if run.tkeir_error else run.tkeir.lookup("NDCG@10")
        bm25_ndcg = run.bm25.lookup("NDCG@10")
        dense_ndcg = run.dense.lookup("NDCG@10")
        tkeir_vs = (
            ("—", "—", "—")
            if tkeir_ndcg is None
            else (
                _delta(tkeir_ndcg, board.get("BM25", 0.0)),
                _delta(tkeir_ndcg, board.get("SPLADE", 0.0)),
                _delta(tkeir_ndcg, board.get("Contriever", 0.0)),
            )
        )
        lines.append(
            f"| {label} | {best_name} | {_fmt(best_score)} | "
            f"{_gap_to_best(tkeir_ndcg, best_score)} | "
            f"{_gap_to_best(bm25_ndcg, best_score)} | "
            f"{_gap_to_best(dense_ndcg, best_score)} | "
            f"{tkeir_vs[0]} | {tkeir_vs[1]} | {tkeir_vs[2]} |"
        )

    lines.extend(["", "## Per-dataset metrics", ""])

    for run in runs:
        title = DATASET_DISPLAY.get(run.name, run.name)
        board = LEADERBOARD_NDCG10.get(run.name, {})
        best_name, best_score = _best_leaderboard(board)
        lines.append(f"### {title} (`{run.name}`)")
        lines.append("")
        if run.error:
            lines.append(f"**Skipped:** {run.error}")
            lines.append("")
            continue

        lines.append(f"- Corpus size: **{run.corpus_size:,}** documents  ")
        lines.append(f"- Test queries: **{run.query_count:,}**")
        lines.append(f"- Dense baseline model: `{run.dense_model}`")
        lines.append(
            f"- **Best published system:** `{best_name}` "
            f"(NDCG@10 = {_fmt(best_score)})"
        )
        if run.tkeir_error:
            lines.append(f"- T-KEIR status: **failed** — {run.tkeir_error}")
            lines.append("- **T-KEIR gap to best:** —")
        else:
            tkeir_ndcg = run.tkeir.lookup("NDCG@10")
            gap = _gap_to_best(tkeir_ndcg, best_score)
            lines.append(
                "- T-KEIR status: **ok** (QueryAnalyzer + Vespa hybrid)"
            )
            lines.append(
                f"- **T-KEIR gap to best ({best_name}):** `{gap}` "
                f"(T-KEIR {_fmt(tkeir_ndcg)} − {_fmt(best_score)})"
            )
        lines.append(
            f"- Local BM25 gap to best: "
            f"`{_gap_to_best(run.bm25.lookup('NDCG@10'), best_score)}`"
        )
        lines.append(
            f"- Local Dense gap to best: "
            f"`{_gap_to_best(run.dense.lookup('NDCG@10'), best_score)}`"
        )
        lines.append("")
        lines.append("| Metric | T-KEIR | Local BM25 | Local Dense |")
        lines.append("|---|---:|---:|---:|")
        for key in ("NDCG@10", "MAP@100", "Recall@100"):
            tkeir_val = None if run.tkeir_error else run.tkeir.lookup(key)
            lines.append(
                f"| {key} | {_fmt(tkeir_val)} | "
                f"{_fmt(run.bm25.lookup(key))} | "
                f"{_fmt(run.dense.lookup(key))} |"
            )
        lines.append("")

        lines.append("#### Error analysis (T-KEIR)")
        lines.append("")
        lines.extend(_render_failures(run.failures_tkeir))
        lines.append("")
        lines.append("#### Error analysis (Local BM25)")
        lines.append("")
        lines.extend(_render_failures(run.failures_bm25))
        lines.append("")
        lines.append("#### Error analysis (Local Dense)")
        lines.append("")
        lines.extend(_render_failures(run.failures_dense))
        lines.append("")
        lines.append("#### Why these failures happen")
        lines.append("")
        lines.append(QUALITATIVE_NOTES.get(run.name, "_No notes._"))
        lines.append("")
        lines.append(
            "For **T-KEIR**, failures additionally reflect hybrid-rank "
            "trade-offs (lexical vs embedding weights), query analysis "
            "term selection, and embedding-provider domain coverage — "
            "not only raw lexical overlap."
        )
        lines.append("")

    lines.extend(
        [
            "## Method notes",
            "",
            "1. Datasets are cached under `./datasets/{name}/` via "
            "`beir.util.download_and_unzip`.",
            "2. **T-KEIR (retrieval only):** BEIR docs → full NLP "
            "(`chunking` + structural `chunk-questions`) → embed + index → "
            "`QueryAnalyzerTask` + Vespa hybrid top-100. **Answer "
            "generation is disabled** (`RetrievalEmbeddingClient` rejects "
            "`LLM.generate`). Multi-chunk hits get a mild evidence boost. "
            "Corpus is reindexed per dataset for a clean ranking surface.",
            "3. Local BM25: `rank_bm25.BM25Okapi` over title+text.",
            f"4. Local dense: BEIR `DenseRetrievalExactSearch` + "
            f"`SentenceBERT('{dense_model}')`, cosine similarity.",
            "5. Metrics: NDCG@10, MAP@100, Recall@100 via "
            "`EvaluateRetrieval.evaluate`.",
            "6. Leaderboard: published BEIR BM25 / SPLADE / Contriever "
            "NDCG@10. **Best published** = max of those three. "
            "**Gap to best** = system_score − best_score (negative = "
            "behind the leaderboard leader).",
            "7. Failure types: false positives (top-3 irrelevant), false "
            "negatives (gold missing from top-100), near misses "
            "(gold ranked 11–100).",
            "",
        ]
    )
    return "\n".join(lines)


def _render_failures(failures: list[FailureCase]) -> list[str]:
    """Format failure cases as Markdown bullets.

    Args:
        failures: Analyzed cases.

    Returns:
        Markdown lines.

    Example:
        >>> _render_failures([])
        ['_No failure examples extracted._']
    """
    if not failures:
        return ["_No failure examples extracted._"]
    labels = {
        "false_positive": "False positive",
        "false_negative": "False negative",
        "near_miss": "Near miss",
    }
    out: list[str] = []
    for case in failures:
        label = labels.get(case.kind, case.kind)
        out.append(
            f"- **{label}** — query `{case.query_id}`: " f"«{case.query_text}»"
        )
        out.append(f"  - {case.detail}")
    return out


def _empty_run(
    name: str,
    dense_model: str,
    *,
    error: str,
    corpus_size: int = 0,
    query_count: int = 0,
) -> DatasetRun:
    """Build a DatasetRun filled with empty metrics and an error.

    Args:
        name: Dataset id.
        dense_model: Dense model name for the report.
        error: Failure message.
        corpus_size: Known corpus size when available.
        query_count: Known query count when available.

    Returns:
        Failed :class:`DatasetRun`.

    Example:
        >>> _empty_run("scifact", "m", error="boom").error
        'boom'
    """
    empty = Metrics()
    return DatasetRun(
        name=name,
        corpus_size=corpus_size,
        query_count=query_count,
        bm25=empty,
        dense=empty,
        tkeir=empty,
        failures_bm25=[],
        failures_dense=[],
        failures_tkeir=[],
        dense_model=dense_model,
        error=error,
    )


def evaluate_dataset(
    name: str,
    datasets_dir: Path,
    dense_model: str,
    batch_size: int,
    skip_dense: bool = False,
    skip_tkeir: bool = False,
    tkeir_language: str = "en",
    tkeir_reindex: bool = True,
    tkeir_index_mode: str = "chunking",
    tkeir_max_docs: int | None = None,
) -> DatasetRun:
    """Download (if needed), retrieve, evaluate, and analyze one dataset.

    Args:
        name: BEIR dataset id.
        datasets_dir: Cache directory for downloads.
        dense_model: Dense encoder model name.
        batch_size: Dense encode batch size.
        skip_dense: When True, skip local dense retrieval.
        skip_tkeir: When True, skip T-KEIR pipeline / Vespa evaluation.
        tkeir_language: Language for QueryAnalyzer pipeline.
        tkeir_reindex: Wipe/redeploy Vespa before indexing this dataset.
        tkeir_index_mode: ``fast`` / ``chunking`` / ``full`` indexing.
        tkeir_max_docs: Optional corpus cap for smoke tests.

    Returns:
        :class:`DatasetRun` (may contain ``error`` / ``tkeir_error``).

    Example:
        >>> evaluate_dataset("scifact", Path("datasets"), "x", 8)  # doctest: +SKIP
    """
    empty = Metrics()
    path = ensure_dataset(name, datasets_dir)
    if path is None:
        return _empty_run(
            name, dense_model, error="download or dataset preparation failed"
        )

    try:
        corpus, queries, qrels = load_dataset(path)
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Failed to load '%s': %s", name, exc)
        return _empty_run(name, dense_model, error=f"load failed: {exc}")

    try:
        bm25_results = run_bm25(corpus, queries, top_k=TOP_K)
        bm25_metrics = evaluate_results(qrels, bm25_results)
        failures_bm25 = analyze_failures(queries, corpus, qrels, bm25_results)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("BM25 failed on '%s'", name)
        return _empty_run(
            name,
            dense_model,
            error=f"BM25 failed: {exc}",
            corpus_size=len(corpus),
            query_count=len(queries),
        )

    dense_metrics = empty
    failures_dense: list[FailureCase] = []
    if skip_dense:
        LOGGER.info("Skipping dense retrieval for '%s'", name)
    else:
        try:
            dense_results = run_dense(
                corpus, queries, model_name=dense_model, batch_size=batch_size
            )
            dense_metrics = evaluate_results(qrels, dense_results)
            failures_dense = analyze_failures(
                queries, corpus, qrels, dense_results
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Dense retrieval failed on '%s'", name)
            failures_dense = [
                FailureCase(
                    kind="false_negative",
                    query_id="-",
                    query_text="(dense run aborted)",
                    detail=str(exc),
                )
            ]

    tkeir_metrics = empty
    failures_tkeir: list[FailureCase] = []
    tkeir_error: str | None = None
    if skip_tkeir:
        LOGGER.info("Skipping T-KEIR pipeline evaluation for '%s'", name)
        tkeir_error = "skipped (--skip-tkeir)"
    else:
        try:
            from thot.tools.search.beir_tkeir import run_tkeir_eval

            LOGGER.info(
                "Running T-KEIR evaluation for '%s' "
                "(index_mode=%s, max_docs=%s)…",
                name,
                tkeir_index_mode,
                tkeir_max_docs,
            )
            tkeir_results = asyncio.run(
                run_tkeir_eval(
                    name,
                    corpus,
                    queries,
                    language=tkeir_language,
                    top_k=TOP_K,
                    reindex=tkeir_reindex,
                    index_mode=tkeir_index_mode,
                    max_docs=tkeir_max_docs,
                )
            )
            tkeir_metrics = evaluate_results(qrels, tkeir_results)
            failures_tkeir = analyze_failures(
                queries, corpus, qrels, tkeir_results
            )
        except KeyboardInterrupt:
            LOGGER.warning(
                "T-KEIR evaluation interrupted (Ctrl+C) on '%s'", name
            )
            tkeir_error = "interrupted (Ctrl+C during indexing/retrieval)"
            failures_tkeir = [
                FailureCase(
                    kind="false_negative",
                    query_id="-",
                    query_text="(tkeir run interrupted)",
                    detail=tkeir_error,
                )
            ]
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("T-KEIR evaluation failed on '%s'", name)
            tkeir_error = str(exc)
            failures_tkeir = [
                FailureCase(
                    kind="false_negative",
                    query_id="-",
                    query_text="(tkeir run aborted)",
                    detail=str(exc),
                )
            ]

    return DatasetRun(
        name=name,
        corpus_size=len(corpus),
        query_count=len(queries),
        bm25=bm25_metrics,
        dense=dense_metrics,
        tkeir=tkeir_metrics,
        failures_bm25=failures_bm25,
        failures_dense=failures_dense,
        failures_tkeir=failures_tkeir,
        dense_model=dense_model,
        tkeir_error=tkeir_error,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the BEIR evaluation tool.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Parsed namespace.

    Example:
        >>> parse_args(["--datasets", "scifact"]).datasets
        ['scifact']
    """
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate T-KEIR pipeline, BM25, and dense retrieval on BEIR "
            "datasets; write evaluation_report.md with leaderboard comparison"
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
        help="Directory for downloaded BEIR datasets (default: ./datasets)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evaluation_report.md"),
        help="Output Markdown report path (default: ./evaluation_report.md)",
    )
    parser.add_argument(
        "--dense-model",
        default=DEFAULT_DENSE_MODEL,
        help=f"SentenceTransformer model (default: {DEFAULT_DENSE_MODEL})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Dense encoding batch size (default: 32)",
    )
    parser.add_argument(
        "--skip-dense",
        action="store_true",
        help="Skip local SentenceTransformer dense baseline",
    )
    parser.add_argument(
        "--skip-tkeir",
        action="store_true",
        help="Skip T-KEIR retrieval / Vespa evaluation",
    )
    parser.add_argument(
        "--tkeir-language",
        default="en",
        help="Language for T-KEIR QueryAnalyzer pipeline (default: en)",
    )
    parser.add_argument(
        "--no-tkeir-reindex",
        action="store_true",
        help="Do not wipe/redeploy Vespa before indexing (unsafe if mixed data)",
    )
    parser.add_argument(
        "--tkeir-index-mode",
        choices=("fast", "chunking", "full"),
        default="chunking",
        help=(
            "T-KEIR indexing depth: fast (raw chunk), chunking (default NLP "
            "+ structural questions; avoids ontology stall), full "
            "(chunk-questions via PipelineRunner, slow)"
        ),
    )
    parser.add_argument(
        "--tkeir-max-docs",
        type=int,
        default=None,
        help="Cap corpus size for T-KEIR indexing (smoke tests)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: evaluate datasets and write the Markdown report.

    Args:
        argv: Optional CLI args for testing.

    Returns:
        Process exit code (0 on success, 1 if all datasets failed).

    Example:
        >>> main(["--datasets", "scifact", "--skip-dense"])  # doctest: +SKIP
        0
    """
    args = parse_args(argv)
    setup_logging(args.verbose)

    LOGGER.info(
        "Starting BEIR evaluation datasets=%s dir=%s skip_tkeir=%s "
        "tkeir_index_mode=%s tkeir_max_docs=%s",
        args.datasets,
        args.datasets_dir.resolve(),
        args.skip_tkeir,
        args.tkeir_index_mode,
        args.tkeir_max_docs,
    )

    runs: list[DatasetRun] = []
    interrupted = False
    try:
        for name in args.datasets:
            LOGGER.info("========== %s ==========", name)
            run = evaluate_dataset(
                name=name,
                datasets_dir=args.datasets_dir,
                dense_model=args.dense_model,
                batch_size=args.batch_size,
                skip_dense=args.skip_dense,
                skip_tkeir=args.skip_tkeir,
                tkeir_language=args.tkeir_language,
                tkeir_reindex=not args.no_tkeir_reindex,
                tkeir_index_mode=args.tkeir_index_mode,
                tkeir_max_docs=args.tkeir_max_docs,
            )
            runs.append(run)
            if run.tkeir_error and run.tkeir_error.startswith("interrupted"):
                interrupted = True
                LOGGER.warning(
                    "Stopping remaining datasets after interrupt"
                )
                break
    except KeyboardInterrupt:
        interrupted = True
        LOGGER.warning(
            "Interrupted — writing report for %d completed dataset(s)",
            len(runs),
        )

    if not runs:
        LOGGER.error("No dataset runs completed")
        return 130

    report = render_report(runs, dense_model=args.dense_model)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    LOGGER.info("Wrote report → %s", args.report.resolve())

    if interrupted:
        # Avoid asyncio default executor join hang after Ctrl+C.
        os._exit(130)

    if all(run.error for run in runs):
        LOGGER.error("All dataset evaluations failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
