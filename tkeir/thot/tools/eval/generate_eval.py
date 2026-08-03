"""Title: Generation eval (generate-eval) — T-KEIR only, oracle evidence.

Selectable corpora under ``datasets/rag_benchmarks/``. For each query:

1. Take the dataset's provided evidence (``evidence_list`` / ``documents``)
2. Analyze the request (full NLP)
3. Analyze those passages (focus windows + passage SVO)
4. Merge query+passage SVO into one ontology (optional reasoner)
5. Detect question type and build **one** unique type-aware QA prompt
6. Single LLM generate call

No retrieval (BM25 / dense / ColBERT). Compares generation quality to
``leaderboard.yaml`` (MultiHop ground-truth accuracy; RAGBench Hal AUROC
shown as reference only).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from thot.core.TkeirPaths import evaluation_generate_report_path, repo_root
from thot.tasks.answer_generation.rag_answer import (
    PassageHit,
    RagAnswerResult,
    answer_contains_gold,
    answer_from_passages,
    build_llm_wrapper,
    normalized_em,
    token_f1,
)
from thot.tools.eval.beir_eval import setup_logging, write_report_file

LOGGER = logging.getLogger(__name__)

DEFAULT_DATASETS = ("covidqa", "pubmedqa", "finqa", "tatqa", "multihop")

DATASET_REGISTRY: dict[str, dict[str, str]] = {
    "covidqa": {
        "family": "ragbench",
        "display": "RAGBench CovidQA",
        "relpath": "ragbench/medical/covidqa",
        "split": "test",
    },
    "pubmedqa": {
        "family": "ragbench",
        "display": "RAGBench PubMedQA",
        "relpath": "ragbench/medical/pubmedqa",
        "split": "test",
    },
    "finqa": {
        "family": "ragbench",
        "display": "RAGBench FinQA",
        "relpath": "ragbench/finance/finqa",
        "split": "test",
    },
    "tatqa": {
        "family": "ragbench",
        "display": "RAGBench TAT-QA",
        "relpath": "ragbench/finance/tatqa",
        "split": "test",
    },
    "multihop": {
        "family": "multihop_rag",
        "display": "MultiHop-RAG",
        "relpath": "multihop_rag",
        "split": "",
    },
}


@dataclass
class GenExample:
    """One generation query with oracle evidence passages.

    Example:
        >>> from thot.tasks.answer_generation.rag_answer import PassageHit
        >>> from thot.tools.eval.generate_eval import GenExample
        >>> GenExample("q1", "What?", "gold", [PassageHit("d", "t", "body")]).query_id
        'q1'
    """

    query_id: str
    query: str
    gold: str
    passages: list[PassageHit]


@dataclass
class GenMetrics:
    """Aggregation of generation quality metrics.

    Example:
        >>> from thot.tools.eval.generate_eval import GenMetrics
        >>> GenMetrics(n=2, em=1.0, f1=0.8).as_dict()["em"]
        0.5
    """

    n: int = 0
    em: float = 0.0
    f1: float = 0.0
    contains: float = 0.0
    errors: int = 0

    def as_dict(self) -> dict[str, float]:
        """Return JSON-serializable averages.

        Returns:
            Dict with ``n``, ``em``, ``f1``, ``contains``, and ``errors`` keys.

        Example:
            >>> from thot.tools.eval.generate_eval import GenMetrics
            >>> GenMetrics(n=0).as_dict()["n"]
            0
        """
        if self.n <= 0:
            return {
                "n": 0,
                "em": 0.0,
                "f1": 0.0,
                "contains": 0.0,
                "errors": self.errors,
            }
        return {
            "n": float(self.n),
            "em": self.em / self.n,
            "f1": self.f1 / self.n,
            "contains": self.contains / self.n,
            "errors": float(self.errors),
        }


@dataclass
class GenDatasetRun:
    """One generation evaluation on a RAG-benchmark corpus.

    Example:
        >>> from thot.tools.eval.generate_eval import GenDatasetRun
        >>> GenDatasetRun("covidqa", "CovidQA", "ragbench", 10, 5).name
        'covidqa'
    """

    name: str
    display: str
    family: str
    evidence_passages: int
    query_count: int
    metrics: GenMetrics = field(default_factory=GenMetrics)
    samples: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


# Back-compat aliases used by older imports / tests.
RagDatasetRun = GenDatasetRun


def default_rag_benchmarks_dir() -> Path:
    """Return ``<repo>/datasets/rag_benchmarks``.

    Example:
        >>> from thot.tools.eval.generate_eval import default_rag_benchmarks_dir
        >>> default_rag_benchmarks_dir().name
        'rag_benchmarks'
    """
    return Path(repo_root()) / "datasets" / "rag_benchmarks"


def default_leaderboard_path(rag_dir: Path | None = None) -> Path:
    """Return path to ``leaderboard.yaml``.

    Args:
        rag_dir: Optional rag_benchmarks root; defaults to
            :func:`default_rag_benchmarks_dir`.

    Example:
        >>> from thot.tools.eval.generate_eval import default_leaderboard_path
        >>> default_leaderboard_path().name
        'leaderboard.yaml'
    """
    base = rag_dir or default_rag_benchmarks_dir()
    return base / "leaderboard.yaml"


def reports_generate_dir() -> Path:
    """Return ``<repo>/reports/generate``.

    Example:
        >>> from thot.tools.eval.generate_eval import reports_generate_dir
        >>> reports_generate_dir().name
        'generate'
    """
    return Path(repo_root()) / "reports" / "generate"


def _emit_progress(message: str) -> None:
    """Write a high-visibility progress line (stderr + WARNING log).

    Args:
        message: Progress text without the ``[gen-eval]`` prefix.

    Example:
        >>> from thot.tools.eval.generate_eval import _emit_progress
        >>> _emit_progress("smoke")  # doctest: +SKIP
    """
    line = f"[gen-eval] {message}"
    print(line, file=sys.stderr, flush=True)
    # WARNING so it cuts through dense INFO NLP/LLM logs.
    LOGGER.warning("%s", message)


def default_prompt_dump_dir(dataset: str) -> Path:
    """Return ``reports/generate/<dataset>/prompts`` under the repo.

    Args:
        dataset: Dataset id used as a subdirectory name.

    Example:
        >>> from thot.tools.eval.generate_eval import default_prompt_dump_dir
        >>> list(default_prompt_dump_dir("covidqa").parts[-2:])
        ['covidqa', 'prompts']
    """
    return reports_generate_dir() / dataset / "prompts"


def safe_prompt_filename(query_id: str) -> str:
    """Sanitize a query id for use as a dump basename.

    Args:
        query_id: Raw query identifier from a benchmark row.

    Returns:
        Filesystem-safe basename truncated to 180 characters.

    Example:
        >>> from thot.tools.eval.generate_eval import safe_prompt_filename
        >>> safe_prompt_filename('q/1 "test"')
        'q_1_test'
    """
    import re

    cleaned = re.sub(r"[^\w.\-]+", "_", str(query_id or "query")).strip("._")
    return (cleaned or "query")[:180]


def dump_llm_prompt(
    dump_dir: Path,
    *,
    dataset: str,
    example: GenExample,
    answer: RagAnswerResult,
    index: int,
    total: int,
) -> Path:
    """Write one JSON prompt dump under ``dump_dir``; return the file path.

    Args:
        dump_dir: Directory where prompt JSON files are written.
        dataset: Dataset id for metadata.
        example: Generation example being evaluated.
        answer: LLM answer result to serialize.
        index: One-based example index within the dataset run.
        total: Total examples in the dataset run.

    Returns:
        Path to the written JSON file.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.tasks.answer_generation.rag_answer import PassageHit, RagAnswerResult
        >>> from thot.tools.eval.generate_eval import GenExample, dump_llm_prompt
        >>> ex = GenExample("q1", "What?", "gold", [PassageHit("d", "t", "body")])
        >>> ans = RagAnswerResult("q1", "What?", "yes", "yes", "prompt")
        >>> with tempfile.TemporaryDirectory() as td:
        ...     path = dump_llm_prompt(Path(td), dataset="ds", example=ex, answer=ans, index=1, total=1)
        ...     path.name
        'q1.json'
    """
    dump_dir.mkdir(parents=True, exist_ok=True)
    path = dump_dir / f"{safe_prompt_filename(example.query_id)}.json"
    payload = {
        "dataset": dataset,
        "index": index,
        "total": total,
        "query_id": example.query_id,
        "query": example.query,
        "gold": example.gold,
        "n_evidence": len(example.passages),
        "forged": answer.forged,
        "question_type": answer.question_type,
        "reasoner_note": answer.reasoner_note,
        "sparql_queries": list(answer.sparql_queries or []),
        "sparql_clues": answer.sparql_clues,
        "system_prompt": answer.system_prompt,
        "user_prompt": answer.user_prompt,
        "input_prompt": answer.input_prompt,
        "short_answer": answer.short_answer,
        "detailed_report": answer.detailed_report,
        "error": answer.error,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_leaderboard(path: Path | None = None) -> dict[str, Any]:
    """Load published RAG leaderboard YAML.

    Args:
        path: Optional leaderboard file; defaults to
            :func:`default_leaderboard_path`.

    Returns:
        Parsed YAML dict, or ``{}`` when the file is missing.

    Example:
        >>> from thot.tools.eval.generate_eval import load_leaderboard
        >>> isinstance(load_leaderboard(), dict)
        True
    """
    target = path or default_leaderboard_path()
    if not target.is_file():
        LOGGER.warning("RAG leaderboard not found at %s", target)
        return {}
    import yaml

    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _load_json_records(path: Path) -> list[dict[str, Any]]:
    """Load a JSON array file into a list of row dicts.

    Args:
        path: Path to a JSON file containing an array of objects.

    Returns:
        Parsed list of dict rows.

    Raises:
        ValueError: When the file root is not a JSON array.

    Example:
        >>> import json, tempfile
        >>> from pathlib import Path
        >>> from thot.tools.eval.generate_eval import _load_json_records
        >>> with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        ...     json.dump([{"id": 1}], handle)
        ...     p = Path(handle.name)
        >>> try:
        ...     _load_json_records(p)[0]["id"]
        ... finally:
        ...     p.unlink()
        1
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON array in {path}")
    return payload


def _title_from_doc(text: str) -> str:
    """Extract a short title line from a RAGBench document block.

    Args:
        text: Raw document text, optionally prefixed with ``Title:``.

    Returns:
        First line title truncated to 200 characters.

    Example:
        >>> from thot.tools.eval.generate_eval import _title_from_doc
        >>> _title_from_doc("Title: My Doc\\nBody")
        'My Doc'
    """
    first = (text or "").split("\n", 1)[0].strip()
    if first.lower().startswith("title:"):
        first = first[6:].strip()
    return first[:200] or "document"


def load_ragbench_split(
    dataset_dir: Path,
    *,
    split: str = "test",
    max_queries: int | None = None,
) -> list[GenExample]:
    """Load RAGBench rows as query + provided ``documents`` evidence.

    Args:
        dataset_dir: Directory containing ``<split>.json``.
        split: Split name (default ``test``).
        max_queries: Optional cap on loaded examples.

    Returns:
        List of :class:`GenExample` rows with oracle passages.

    Example:
        >>> import json, tempfile
        >>> from pathlib import Path
        >>> from thot.tools.eval.generate_eval import load_ragbench_split
        >>> with tempfile.TemporaryDirectory() as td:
        ...     p = Path(td)
        ...     _ = (p / "test.json").write_text(json.dumps([{
        ...         "id": "q1", "question": "What?", "response": "Answer",
        ...         "documents": ["Title: Doc\\nBody text"]
        ...     }]), encoding="utf-8")
        ...     load_ragbench_split(p)[0].query_id
        'q1'
    """
    json_path = dataset_dir / f"{split}.json"
    if not json_path.is_file():
        raise FileNotFoundError(json_path)
    rows = _load_json_records(json_path)
    examples: list[GenExample] = []

    for row in rows:
        qid = str(row.get("id") or f"q_{len(examples)}")
        question = str(row.get("question") or "").strip()
        documents = row.get("documents") or []
        answer = str(row.get("response") or "").strip()
        if not question or not isinstance(documents, list) or not documents:
            continue
        passages: list[PassageHit] = []
        for doc_idx, doc_text in enumerate(documents):
            text = str(doc_text or "").strip()
            if not text:
                continue
            passages.append(
                PassageHit(
                    doc_id=f"{qid}_doc_{doc_idx}",
                    title=_title_from_doc(text),
                    text=text,
                    score=1.0,
                )
            )
        if not passages:
            continue
        examples.append(
            GenExample(
                query_id=qid,
                query=question,
                gold=answer,
                passages=passages,
            )
        )
        if max_queries is not None and len(examples) >= max_queries:
            break
    return examples


def load_multihop_rag(
    dataset_dir: Path,
    *,
    max_queries: int | None = None,
    include_null: bool = False,
) -> list[GenExample]:
    """Load MultiHop-RAG using ``evidence_list`` facts (no corpus retrieve).

    Args:
        dataset_dir: Directory containing ``MultiHopRAG.json``.
        max_queries: Optional cap on loaded examples.
        include_null: When False, skip ``null_query`` rows.

    Returns:
        List of :class:`GenExample` rows with oracle evidence passages.

    Example:
        >>> import json, tempfile
        >>> from pathlib import Path
        >>> from thot.tools.eval.generate_eval import load_multihop_rag
        >>> row = {"query": "Who?", "answer": "Alice", "evidence_list": [
        ...     {"title": "News", "fact": "Alice works at Acme", "source": "web"}
        ... ]}
        >>> with tempfile.TemporaryDirectory() as td:
        ...     p = Path(td)
        ...     _ = (p / "MultiHopRAG.json").write_text(json.dumps([row]), encoding="utf-8")
        ...     load_multihop_rag(p)[0].gold
        'Alice'
    """
    qa_rows = _load_json_records(dataset_dir / "MultiHopRAG.json")
    examples: list[GenExample] = []
    for index, row in enumerate(qa_rows):
        qtype = str(row.get("question_type") or "")
        if qtype == "null_query" and not include_null:
            continue
        query = str(row.get("query") or "").strip()
        evidence = row.get("evidence_list") or []
        answer = str(row.get("answer") or "").strip()
        if not query or not isinstance(evidence, list) or not evidence:
            continue
        passages: list[PassageHit] = []
        for ev_idx, item in enumerate(evidence):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            fact = str(item.get("fact") or "").strip()
            source = str(item.get("source") or "").strip()
            text = fact or title
            if not text:
                continue
            if source and title:
                display = f"{title} ({source})"
            else:
                display = title or source or f"evidence_{ev_idx}"
            passages.append(
                PassageHit(
                    doc_id=f"mh_q_{index}_ev_{ev_idx}",
                    title=display,
                    text=text,
                    score=1.0,
                )
            )
        if not passages:
            continue
        examples.append(
            GenExample(
                query_id=f"mh_q_{index}",
                query=query,
                gold=answer,
                passages=passages,
            )
        )
        if max_queries is not None and len(examples) >= max_queries:
            break
    return examples


def load_gen_dataset(
    name: str,
    rag_dir: Path,
    *,
    max_queries: int | None = None,
) -> list[GenExample]:
    """Dispatch loader for a selectable generation-eval dataset id.

    Args:
        name: Dataset id from :data:`DATASET_REGISTRY`.
        rag_dir: Root ``rag_benchmarks`` directory.
        max_queries: Optional cap on loaded examples.

    Returns:
        Loaded :class:`GenExample` list for the dataset.

    Raises:
        KeyError: When ``name`` is unknown.
        FileNotFoundError: When the dataset directory is missing.

    Example:
        >>> import json, tempfile
        >>> from pathlib import Path
        >>> from thot.tools.eval.generate_eval import load_gen_dataset
        >>> with tempfile.TemporaryDirectory() as td:
        ...     root = Path(td)
        ...     ds = root / "ragbench" / "medical" / "covidqa"
        ...     ds.mkdir(parents=True)
        ...     _ = (ds / "test.json").write_text(json.dumps([{
        ...         "id": "q1", "question": "Q?", "response": "A",
        ...         "documents": ["body"]
        ...     }]), encoding="utf-8")
        ...     load_gen_dataset("covidqa", root)[0].query
        'Q?'
    """
    meta = DATASET_REGISTRY.get(name)
    if meta is None:
        known = ", ".join(sorted(DATASET_REGISTRY))
        raise KeyError(f"Unknown dataset {name!r}; choose from: {known}")
    path = rag_dir / meta["relpath"]
    if not path.is_dir():
        raise FileNotFoundError(
            f"Dataset directory missing: {path}. "
            "Run: python datasets/download_rag_datasets.py"
        )
    if meta["family"] == "multihop_rag":
        return load_multihop_rag(path, max_queries=max_queries)
    return load_ragbench_split(
        path, split=meta.get("split") or "test", max_queries=max_queries
    )


# Back-compat name.
load_rag_dataset = load_gen_dataset


def _fmt(value: float | None, digits: int = 3) -> str:
    """Format a metric for Markdown tables.

    Args:
        value: Numeric metric or ``None``.
        digits: Decimal places when formatting floats.

    Returns:
        Fixed-width string, or em dash when ``value`` is ``None``.

    Example:
        >>> from thot.tools.eval.generate_eval import _fmt
        >>> _fmt(0.665)
        '0.665'
    """
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def _delta(ours: float | None, baseline: float | None) -> str:
    """Format a signed gap between two scores.

    Args:
        ours: T-KEIR score.
        baseline: Published baseline score.

    Returns:
        Signed delta string, or em dash when either input is ``None``.

    Example:
        >>> from thot.tools.eval.generate_eval import _delta
        >>> _delta(0.70, 0.665)
        '+0.035'
    """
    if ours is None or baseline is None:
        return "—"
    return f"{ours - baseline:+.3f}"


def _multihop_gen_best(board: dict[str, Any]) -> tuple[str, float] | None:
    """Prefer GPT-4 *ground-truth evidence* accuracy (matches oracle path).

    Args:
        board: Parsed ``leaderboard.yaml`` payload.

    Returns:
        ``(system_name, score)`` tuple, or ``None`` when unavailable.

    Example:
        >>> from thot.tools.eval.generate_eval import _multihop_gen_best
        >>> board = {"datasets": {"multihop_rag": {"generation": {
        ...     "models": {"GPT-4": {"accuracy_ground_truth": 0.55}}
        ... }}}}
        >>> _multihop_gen_best(board)
        ('GPT-4 (ground-truth evidence)', 0.55)
    """
    gen = ((board.get("datasets") or {}).get("multihop_rag") or {}).get(
        "generation"
    ) or {}
    models = gen.get("models") or {}
    gpt4 = models.get("GPT-4") or {}
    gt = gpt4.get("accuracy_ground_truth")
    if isinstance(gt, (int, float)):
        return "GPT-4 (ground-truth evidence)", float(gt)
    retrieved = gpt4.get("accuracy_retrieved")
    if isinstance(retrieved, (int, float)):
        return "GPT-4 (retrieved chunks)", float(retrieved)
    best = ((board.get("best_published") or {}).get("multihop_rag") or {}).get(
        "generation"
    )
    if isinstance(best, dict) and isinstance(best.get("score"), (int, float)):
        return str(best.get("system") or "best"), float(best["score"])
    return None


def _ragbench_hal_best(
    board: dict[str, Any], subset: str
) -> tuple[str, float] | None:
    """Return the best published RAGBench Hal AUROC for one subset.

    Args:
        board: Parsed ``leaderboard.yaml`` payload.
        subset: RAGBench subset id (for example ``covidqa``).

    Returns:
        ``(system_name, score)`` tuple, or ``None`` when unavailable.

    Example:
        >>> from thot.tools.eval.generate_eval import _ragbench_hal_best
        >>> board = {"best_published": {"ragbench": {"by_subset": {
        ...     "covidqa": {"system": "best", "score": 0.88}
        ... }}}}
        >>> _ragbench_hal_best(board, "covidqa")
        ('best', 0.88)
    """
    by_subset = (
        (board.get("best_published") or {}).get("ragbench") or {}
    ).get("by_subset") or {}
    entry = by_subset.get(subset) or {}
    score = entry.get("score")
    if isinstance(score, (int, float)):
        return str(entry.get("system") or "best"), float(score)
    return None


def render_report(
    runs: list[GenDatasetRun],
    *,
    leaderboard: dict[str, Any],
    forge_prompt: bool,
) -> str:
    """Build Markdown report: T-KEIR generation vs published leaderboard.

    Args:
        runs: Completed dataset evaluation runs.
        leaderboard: Parsed ``leaderboard.yaml`` payload.
        forge_prompt: Whether prompt forging was enabled.

    Returns:
        Markdown report body.

    Example:
        >>> from thot.tools.eval.generate_eval import render_report
        >>> "# Generation Evaluation Report" in render_report([], leaderboard={}, forge_prompt=False)
        True
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "# Generation Evaluation Report",
        "",
        f"_Generated {now}_",
        "",
        "T-KEIR-only **generation** eval on `datasets/rag_benchmarks/`: "
        "oracle evidence → NLP → merged query/passage ontology → "
        "unique type-aware prompt → "
        f"{'optional forge + ' if forge_prompt else ''}"
        "LLM answer. No retrieval. Compared to `leaderboard.yaml`.",
        "",
        "## Summary vs leaderboard",
        "",
        "| Dataset | Metric | T-KEIR | Published | Gap |",
        "|---------|--------|-------:|----------:|----:|",
    ]
    for run in runs:
        if run.error:
            lines.append(f"| {run.display} | — | error | — | — |")
            continue
        stats = run.metrics.as_dict()
        if run.family == "multihop_rag":
            ours = stats["contains"]
            best = _multihop_gen_best(leaderboard)
            best_score = best[1] if best else None
            best_name = best[0] if best else "—"
            lines.append(
                f"| {run.display} | Acc (contains) | {_fmt(ours)} | "
                f"{_fmt(best_score)} ({best_name}) | "
                f"{_delta(ours, best_score)} |"
            )
        else:
            best = _ragbench_hal_best(leaderboard, run.name)
            best_score = best[1] if best else None
            best_name = best[0] if best else "—"
            lines.append(
                f"| {run.display} | F1 (vs gold response) | "
                f"{_fmt(stats['f1'])} | "
                f"Hal AUROC {_fmt(best_score)} ({best_name})* | n/a |"
            )
    lines.extend(
        [
            "",
            "\\* RAGBench published Hal AUROC is a *judge* metric — reference only.",
            "",
            "## Per-dataset generation metrics",
            "",
        ]
    )
    for run in runs:
        lines.append(f"### {run.display} (`{run.name}`)")
        lines.append("")
        if run.error:
            lines.append(f"**Error:** {run.error}")
            lines.append("")
            continue
        stats = run.metrics.as_dict()
        lines.append(
            f"Evidence passages **{run.evidence_passages:,}** · queries "
            f"**{run.query_count:,}** · errors **{int(stats['errors'])}**"
        )
        lines.append("")
        lines.append("| EM | Token F1 | Contains-gold |")
        lines.append("|---:|---------:|--------------:|")
        lines.append(
            f"| {_fmt(stats['em'])} | {_fmt(stats['f1'])} | "
            f"{_fmt(stats['contains'])} |"
        )
        lines.append("")
        if run.samples:
            lines.append("**Sample answers**")
            lines.append("")
            for sample in run.samples[:3]:
                lines.append(f"- Q: {sample.get('query', '')[:160]}")
                lines.append(f"  - gold: `{sample.get('gold', '')[:120]}`")
                lines.append(
                    f"  - pred: `{sample.get('pred', '')[:120]}` "
                    f"(F1={_fmt(sample.get('f1'))})"
                )
            lines.append("")
    lines.extend(
        [
            "## Method",
            "",
            "1. Use dataset oracle evidence only "
            "(`evidence_list` facts / RAGBench `documents`).",
            "2. Full NLP analysis of the request + passage SVO.",
            "3. Merge query+passage SVO into one ontology; optional reasoner.",
            "4. Detect question type (yes/no, wh-, inference, …).",
            "5. Build one unique type-aware QA prompt with relevant ontology facts.",
            "6. Generate SHORT_ANSWER / DETAILED_REPORT via a single LLM call.",
            "7. Score EM / token-F1 / contains-gold vs dataset answers.",
            "",
        ]
    )
    return "\n".join(lines)


def save_reports(
    runs: list[GenDatasetRun],
    *,
    leaderboard: dict[str, Any],
    forge_prompt: bool,
    docs_report: Path,
    extra_report: Path | None = None,
    latest_dataset: str | None = None,
    expected_total: int | None = None,
) -> None:
    """Write docs + ``reports/generate/`` copies.

    Args:
        runs: Completed dataset evaluation runs.
        leaderboard: Parsed ``leaderboard.yaml`` payload.
        forge_prompt: Whether prompt forging was enabled.
        docs_report: Primary Markdown report path under ``docs/``.
        extra_report: Optional additional report destination.
        latest_dataset: Dataset id for per-dataset report refresh.
        expected_total: Expected dataset count for intermediate banners.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.tools.eval.generate_eval import save_reports
        >>> with tempfile.TemporaryDirectory() as td:
        ...     save_reports([], leaderboard={}, forge_prompt=False, docs_report=Path(td) / "r.md")
        ...     (Path(td) / "r.md").exists()
        True
    """
    body = render_report(
        runs, leaderboard=leaderboard, forge_prompt=forge_prompt
    )
    if (
        expected_total is not None
        and expected_total > 0
        and len(runs) < expected_total
    ):
        banner = (
            f"> **Intermediate:** {len(runs)}/{expected_total} dataset(s) "
            "completed so far.\n\n"
        )
        marker = "_Generated "
        idx = body.find(marker)
        if idx != -1:
            end = body.find("\n", idx)
            body = (
                body[: end + 1] + "\n" + banner + body[end + 1 :]
                if end != -1
                else banner + body
            )
        else:
            body = banner + body

    write_report_file(docs_report, body)
    reports_root = reports_generate_dir()
    write_report_file(reports_root / "report.md", body)
    if latest_dataset:
        single = [run for run in runs if run.name == latest_dataset]
        if single:
            write_report_file(
                reports_root / latest_dataset / "report.md",
                render_report(
                    single, leaderboard=leaderboard, forge_prompt=forge_prompt
                ),
            )
    if extra_report is not None:
        extra = Path(extra_report)
        if extra.resolve() != docs_report.resolve():
            write_report_file(extra, body)


async def _evaluate_dataset_async(
    name: str,
    rag_dir: Path,
    *,
    language: str,
    max_queries: int | None,
    forge_prompt: bool,
    use_reasoner: bool,
    use_ontology: bool,
    skip_nlp: bool,
    sample_answers: int,
    dump_prompts_dir: Path | None = None,
) -> GenDatasetRun:
    """Async evaluation of one dataset (oracle evidence → generate).

    Args:
        name: Dataset id from :data:`DATASET_REGISTRY`.
        rag_dir: Root ``rag_benchmarks`` directory.
        language: NLP / prompt language code.
        max_queries: Optional cap on loaded examples.
        forge_prompt: Whether to run legacy prompt forging.
        use_reasoner: Whether to run the ontology reasoner.
        use_ontology: Whether to merge document ontology.
        skip_nlp: When True, skip :class:`PipelineRunner` NLP.
        sample_answers: Sample Q/A pairs to retain in the run.
        dump_prompts_dir: Optional directory for per-query prompt dumps.

    Returns:
        Completed :class:`GenDatasetRun` with metrics and samples.

    Example:
        >>> from pathlib import Path
        >>> from thot.tools.eval.generate_eval import _evaluate_dataset_async
        >>> import asyncio
        >>> asyncio.run(_evaluate_dataset_async(  # doctest: +SKIP
        ...     "covidqa", Path("datasets/rag_benchmarks"), language="en",
        ...     max_queries=1, forge_prompt=False, use_reasoner=False,
        ...     use_ontology=False, skip_nlp=True, sample_answers=1,
        ... ))
    """
    meta = DATASET_REGISTRY[name]
    try:
        examples = load_gen_dataset(name, rag_dir, max_queries=max_queries)
    except Exception as exc:  # noqa: BLE001
        return GenDatasetRun(
            name=name,
            display=meta["display"],
            family=meta["family"],
            evidence_passages=0,
            query_count=0,
            error=str(exc),
        )

    if not examples:
        return GenDatasetRun(
            name=name,
            display=meta["display"],
            family=meta["family"],
            evidence_passages=0,
            query_count=0,
            error="empty examples",
        )

    evidence_n = sum(len(ex.passages) for ex in examples)
    total = len(examples)
    LOGGER.info(
        "generate-eval %s: %d queries, %d evidence passages "
        "(forge=%s ontology=%s nlp=%s)",
        name,
        total,
        evidence_n,
        forge_prompt,
        use_ontology,
        not skip_nlp,
    )
    if dump_prompts_dir is not None:
        dump_prompts_dir.mkdir(parents=True, exist_ok=True)
        LOGGER.info("Dumping LLM prompts → %s", dump_prompts_dir)

    from thot.tools.eval.beir_tkeir import load_pipeline_runner

    runner = (
        None if skip_nlp else await asyncio.to_thread(load_pipeline_runner)
    )
    llm = build_llm_wrapper()

    metrics = GenMetrics()
    samples: list[dict[str, Any]] = []
    try:
        import time

        _emit_progress(
            f"generate-eval [{name}] starting {total} request(s) "
            f"(forge={forge_prompt})"
        )
        for index, example in enumerate(examples, start=1):
            _emit_progress(
                f"generate-eval [{name}] {index}/{total} "
                f"start {example.query_id}"
            )
            started = time.perf_counter()
            answer: RagAnswerResult = await answer_from_passages(
                example.query_id,
                example.query,
                example.passages,
                llm=llm,
                runner=runner,
                language=language,
                forge_prompt=forge_prompt,
                use_reasoner=use_reasoner,
                use_ontology=use_ontology,
            )
            elapsed = time.perf_counter() - started
            qtype = getattr(answer, "question_type", "") or ""
            status = "error" if answer.error else "ok"
            _emit_progress(
                f"generate-eval [{name}] {index}/{total} "
                f"done {example.query_id} ({status}"
                f"{', ' + qtype if qtype else ''}, {elapsed:.1f}s)"
            )
            if dump_prompts_dir is not None:
                dump_llm_prompt(
                    dump_prompts_dir,
                    dataset=name,
                    example=example,
                    answer=answer,
                    index=index,
                    total=total,
                )
            gold_text = example.gold
            if answer.error:
                metrics.errors += 1
                continue
            metrics.n += 1
            em = normalized_em(answer.short_answer, gold_text)
            f1 = token_f1(answer.short_answer, gold_text)
            contains = answer_contains_gold(answer.short_answer, gold_text)
            f1 = max(f1, token_f1(answer.detailed_report, gold_text))
            contains = max(
                contains,
                answer_contains_gold(answer.detailed_report, gold_text),
            )
            metrics.em += em
            metrics.f1 += f1
            metrics.contains += contains
            if len(samples) < sample_answers:
                samples.append(
                    {
                        "query": example.query,
                        "gold": gold_text,
                        "pred": answer.short_answer,
                        "f1": f1,
                        "forged": answer.forged,
                        "question_type": qtype,
                        "n_evidence": len(example.passages),
                    }
                )
    finally:
        await llm.aclose()

    _emit_progress(
        f"generate-eval [{name}] finished {metrics.n}/{total} answered "
        f"({metrics.errors} errors)"
    )
    LOGGER.info(
        "generate-eval %s: done %d/%d answered (%d errors)",
        name,
        metrics.n,
        total,
        metrics.errors,
    )
    return GenDatasetRun(
        name=name,
        display=meta["display"],
        family=meta["family"],
        evidence_passages=evidence_n,
        query_count=len(examples),
        metrics=metrics,
        samples=samples,
    )


def evaluate_dataset(
    name: str,
    rag_dir: Path,
    **kwargs: Any,
) -> GenDatasetRun:
    """Sync wrapper around async dataset evaluation.

    Args:
        name: Dataset id from :data:`DATASET_REGISTRY`.
        rag_dir: Root ``rag_benchmarks`` directory.
        **kwargs: Forwarded to :func:`_evaluate_dataset_async`.

    Returns:
        Completed :class:`GenDatasetRun`.

    Example:
        >>> from pathlib import Path
        >>> from thot.tools.eval.generate_eval import evaluate_dataset
        >>> evaluate_dataset(  # doctest: +SKIP
        ...     "covidqa", Path("datasets/rag_benchmarks"),
        ...     max_queries=1, skip_nlp=True, forge_prompt=False,
        ...     use_ontology=False, use_reasoner=False, sample_answers=1,
        ... )
    """
    return asyncio.run(_evaluate_dataset_async(name, rag_dir, **kwargs))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for generation eval.

    Args:
        argv: Optional argument list; defaults to ``sys.argv``.

    Returns:
        Parsed CLI namespace.

    Example:
        >>> from thot.tools.eval.generate_eval import parse_args
        >>> parse_args(["--datasets", "covidqa"]).datasets
        ['covidqa']
    """
    parser = argparse.ArgumentParser(
        description=(
            "T-KEIR-only generation eval on rag_benchmarks "
            "(oracle evidence → NLP → ontology → forge prompt → LLM)"
        )
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=list(DEFAULT_DATASETS),
        choices=sorted(DATASET_REGISTRY),
        help=f"Dataset ids (default: {' '.join(DEFAULT_DATASETS)})",
    )
    parser.add_argument(
        "--rag-dir",
        type=Path,
        default=None,
        help=f"rag_benchmarks root (default: {default_rag_benchmarks_dir()})",
    )
    parser.add_argument(
        "--leaderboard",
        type=Path,
        default=None,
        help="Path to leaderboard.yaml",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional extra Markdown report path",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="NLP / prompt language (default: en)",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=None,
        help="Cap queries per dataset (smoke)",
    )
    parser.add_argument(
        "--forge-prompt",
        action="store_true",
        help=(
            "Optional legacy LLM prompt-forge (off by default). "
            "Prefer the unique ontology-grounded prompt."
        ),
    )
    parser.add_argument(
        "--no-forge-prompt",
        action="store_true",
        help=argparse.SUPPRESS,  # backward-compatible no-op
    )
    parser.add_argument(
        "--no-reasoner",
        action="store_true",
        help="Skip ontology reasoner (overrides rag.yaml answer_generation.use_reasoner)",
    )
    parser.add_argument(
        "--no-ontology",
        action="store_true",
        help=(
            "Skip document_ontology merge + SPARQL clues "
            "(overrides rag.yaml answer_generation.use_ontology)"
        ),
    )
    parser.add_argument(
        "--skip-nlp",
        action="store_true",
        help=(
            "Skip PipelineRunner NLP "
            "(overrides rag.yaml answer_generation.use_nlp)"
        ),
    )
    parser.add_argument(
        "--sample-answers",
        type=int,
        default=3,
        help="Sample Q/A pairs to include in the report",
    )
    parser.add_argument(
        "--dump-prompts",
        action="store_true",
        help=(
            "Write per-query LLM prompt JSON dumps under "
            "reports/generate/<dataset>/prompts (or --dump-prompts-dir)"
        ),
    )
    parser.add_argument(
        "--dump-prompts-dir",
        type=Path,
        default=None,
        help=(
            "Directory for prompt dumps (implies --dump-prompts). "
            "Default: reports/generate/<dataset>/prompts"
        ),
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry: T-KEIR generation eval + leaderboard report.

    Args:
        argv: Optional argument list; defaults to ``sys.argv``.

    Returns:
        Process exit code (``0`` on success, ``1`` when all datasets fail).

    Example:
        >>> from thot.tools.eval.generate_eval import main
        >>> main(["--datasets", "covidqa", "--max-queries", "1", "--skip-nlp"])  # doctest: +SKIP
        0
    """
    args = parse_args(argv)
    setup_logging(args.verbose)
    rag_dir = (
        Path(args.rag_dir) if args.rag_dir else default_rag_benchmarks_dir()
    )
    leaderboard = load_leaderboard(
        Path(args.leaderboard)
        if args.leaderboard
        else default_leaderboard_path(rag_dir)
    )
    docs_report = Path(evaluation_generate_report_path())
    forge_prompt = bool(args.forge_prompt)
    dump_prompts = bool(args.dump_prompts or args.dump_prompts_dir)

    from thot.tools.search.rag_config import load_rag_config

    answer_cfg = load_rag_config().answer_generation
    use_nlp = bool(answer_cfg.use_nlp) and not bool(args.skip_nlp)
    use_ontology = bool(answer_cfg.use_ontology) and not bool(args.no_ontology)
    use_reasoner = (
        bool(answer_cfg.use_reasoner)
        and use_ontology
        and not bool(args.no_reasoner)
    )

    LOGGER.info(
        "Starting generate-eval datasets=%s forge=%s nlp=%s ontology=%s "
        "reasoner=%s dump_prompts=%s",
        args.datasets,
        forge_prompt,
        use_nlp,
        use_ontology,
        use_reasoner,
        dump_prompts,
    )

    runs: list[GenDatasetRun] = []
    expected = len(args.datasets)
    for name in args.datasets:
        dump_dir: Path | None = None
        if dump_prompts:
            dump_dir = (
                Path(args.dump_prompts_dir)
                if args.dump_prompts_dir
                else default_prompt_dump_dir(name)
            )
            if args.dump_prompts_dir and expected > 1:
                dump_dir = dump_dir / name
        run = evaluate_dataset(
            name,
            rag_dir,
            language=args.language,
            max_queries=args.max_queries,
            forge_prompt=forge_prompt,
            use_reasoner=use_reasoner,
            use_ontology=use_ontology,
            skip_nlp=not use_nlp,
            sample_answers=args.sample_answers,
            dump_prompts_dir=dump_dir,
        )
        runs.append(run)
        save_reports(
            runs,
            leaderboard=leaderboard,
            forge_prompt=forge_prompt,
            docs_report=docs_report,
            extra_report=args.report,
            latest_dataset=name,
            expected_total=expected,
        )

    failed = sum(1 for run in runs if run.error)
    if failed == expected:
        LOGGER.error("All generation datasets failed")
        return 1
    if failed:
        LOGGER.warning("%d / %d dataset(s) failed", failed, expected)
    LOGGER.info("Wrote report → %s", docs_report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
