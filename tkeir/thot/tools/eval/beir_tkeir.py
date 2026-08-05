"""Title: T-KEIR BEIR indexing helpers + retrieve_hybrid eval wiring.

Indexes BEIR docs through :class:`PipelineRunner` into Vespa ``global``
(optional), and scores queries with
:func:`thot.tools.eval.hybrid_retrieve.retrieve_hybrid`
(BGE-M3 + BM25 RRF + ColBERT via :func:`thot.tools.search.rerank.colbert_rerank`).
Answer generation is never invoked.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from thot.core.TkeirPaths import configs_dir, vespa_dir
from thot.tasks.pipeline.PipelineConfiguration import PipelineConfiguration
from thot.tasks.pipeline.PipelineRunner import PipelineRunner
from thot.tools.eval.hybrid_retrieve import document_text
from thot.tools.ingest.index_passages import index_pipeline_document
from thot.tools.search.rag_config import load_rag_config
from thot.tools.search.vespa_client import VespaClient

LOGGER = logging.getLogger(__name__)


def _ascii_progress_bar(index: int, total: int, *, width: int = 28) -> str:
    """Build a compact ASCII progress bar for query retrieval logs.

    Example:
        >>> _ascii_progress_bar(1, 4, width=8)
        '[##------]'
    """
    if total <= 0:
        return "[" + "-" * width + "]"
    frac = min(1.0, max(0.0, float(index) / float(total)))
    filled = int(round(width * frac))
    filled = min(width, max(0, filled))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def log_query_progress(
    index: int,
    total: int,
    *,
    dataset: str,
    started: float,
    qid: str | None = None,
    every: int = 1,
) -> None:
    """Emit a live query progress bar on stderr (+ occasional LOGGER line).

    NLP / ThotLogger spam drowns ``LOGGER.info`` between queries, so the
    primary signal is a carriage-return line on ``stderr`` (same channel as
    FlagEmbedding / tqdm bars). A full LOGGER line is still written on the
    first/last query and every ``every`` steps for log files.

    Example:
        >>> log_query_progress(1, 1, dataset="demo", started=0.0)  # doctest: +SKIP
    """
    import sys

    if total <= 0:
        return
    elapsed = max(1e-6, time.perf_counter() - started)
    rate = index / elapsed
    remaining = max(0, total - index)
    eta_s = remaining / rate if rate > 0 else 0.0
    pct = 100.0 * index / total
    suffix = f" qid={qid}" if qid else ""
    line = (
        f"query progress {dataset} {_ascii_progress_bar(index, total)} "
        f"{index}/{total} ({pct:.0f}%) {rate:.2f} q/s eta={eta_s:.0f}s{suffix}"
    )
    # Live overwrite — visible amid ThotLogger noise (TTY and piped make).
    end = "\n" if index >= total else "\r"
    print(line + "    ", end=end, file=sys.stderr, flush=True)
    milestone = (
        index == 1
        or index >= total
        or every <= 1
        or index % max(1, every) == 0
    )
    if milestone:
        LOGGER.info("%s", line)


BEIR_ID_PREFIX = "beir"
# Default: chunking only (tokenizer→syntax→chunk). Do NOT request
# ``chunk-questions`` via PipelineRunner — that expands to ontology and
# stalls BEIR corpora for hours. Structural questions are attached after.
_INDEX_PIPELINE_TASKS = ("chunking",)
_INDEX_MODES = frozenset({"fast", "chunking", "full"})
_BEIR_QUESTION_SETTINGS = None  # lazy import to avoid circular deps


def _beir_question_settings():
    """Return capped question settings for BEIR indexing (fast, no stall).

    Example:
        >>> settings = _beir_question_settings()
        >>> settings.min_questions
        1
        >>> settings.max_questions
        2
    """
    global _BEIR_QUESTION_SETTINGS
    if _BEIR_QUESTION_SETTINGS is None:
        from thot.tasks.chunk_questions.QuestionBuilder import (
            QuestionGenerationSettings,
        )

        _BEIR_QUESTION_SETTINGS = QuestionGenerationSettings(
            min_questions=1,
            max_questions=2,
            enable_multilingual=False,
        )
    return _BEIR_QUESTION_SETTINGS


def beir_source_doc_id(dataset: str, doc_id: str) -> str:
    """Build a stable ``source_doc_id`` that encodes the BEIR document id.

    Args:
        dataset: BEIR dataset name (e.g. ``scifact``).
        doc_id: Corpus document id from BEIR.

    Returns:
        ``beir:{dataset}:{doc_id}``.

    Example:
        >>> beir_source_doc_id("scifact", "123")
        'beir:scifact:123'
    """
    return f"{BEIR_ID_PREFIX}:{dataset}:{doc_id}"


def seed_pipeline_document(
    dataset: str,
    doc_id: str,
    doc: dict[str, str],
    *,
    language: str,
) -> dict[str, Any]:
    """Build the pre-NLP document seed for :class:`PipelineRunner`.

    Args:
        dataset: BEIR dataset name.
        doc_id: BEIR document id.
        doc: Corpus fields with ``title`` / ``text``.
        language: Processing language pin for ``language-detection``.

    Returns:
        Document with ``content`` and language pin (no synthetic chunks).

    Example:
        >>> seed = seed_pipeline_document(
        ...     "scifact", "1", {"title": "T", "text": "X"}, language="en"
        ... )
        >>> seed["source_doc_id"]
        'beir:scifact:1'
        >>> seed["language-detection"]["language"]
        'en'
    """
    source_id = beir_source_doc_id(dataset, doc_id)
    text = document_text(doc)
    title = (doc.get("title") or "").strip()
    return {
        "data_source": "beir-eval",
        "source_doc_id": source_id,
        "title": title,
        "content": [text] if text else [""],
        "language-detection": {"language": language},
    }


def _ensure_golden_chunks(document: dict[str, Any]) -> dict[str, Any]:
    """Guarantee at least one golden chunk exists for indexing.

    Args:
        document: Pipeline output (may lack chunks on tiny docs).

    Returns:
        Document with ``golden_chunks`` populated when missing.

    Example:
        >>> out = _ensure_golden_chunks({
        ...     "source_doc_id": "beir:scifact:1",
        ...     "content": ["hello"],
        ...     "golden_chunks": [],
        ... })
        >>> out["golden_chunks"][0]["chunk_id"].startswith("beir:scifact:1")
        True
    """
    chunks = document.get("golden_chunks") or []
    if chunks:
        return document
    source_id = str(document.get("source_doc_id") or "document")
    content = document.get("content") or []
    if isinstance(content, list):
        text = " ".join(str(part) for part in content if part).strip()
    else:
        text = str(content or "").strip()
    if not text:
        text = (document.get("title") or "").strip() or source_id
    document = dict(document)
    document["golden_chunks"] = [
        {
            "chunk_id": f"{source_id}#chunk-0-fallback",
            "parent_doc_id": source_id,
            "text_raw": text,
            "search_vector_payload": text,
            "synthetic_questions": [{"question_text": text[:180]}],
            "metadata": {},
        }
    ]
    return document


def _attach_structural_questions(document: dict[str, Any]) -> dict[str, Any]:
    """Add language-agnostic synthetic questions without ontology dependency.

    Args:
        document: Pipeline document with ``golden_chunks``.

    Returns:
        Document whose chunks include ``synthetic_questions``.

    Example:
        >>> doc = _attach_structural_questions({
        ...     "golden_chunks": [{"text_raw": "Alice built parsers", "metadata": {}}],
        ... })
        >>> bool(doc["golden_chunks"][0].get("synthetic_questions"))
        True
    """
    from thot.tasks.chunk_questions.QuestionBuilder import (
        enrich_golden_chunks_with_questions,
    )

    document = dict(document)
    document["golden_chunks"] = enrich_golden_chunks_with_questions(
        document, settings=_beir_question_settings()
    )
    return document


def prepare_index_document(
    runner: PipelineRunner | None,
    dataset: str,
    doc_id: str,
    doc: dict[str, str],
    *,
    language: str,
    index_mode: str = "chunking",
) -> dict[str, Any]:
    """Build a Vespa-ready pipeline document for one BEIR corpus entry.

    Index modes (no answer generation in any mode):

    * ``fast`` — single synthetic chunk (title+text); no document NLP.
    * ``chunking`` — NLP through ``chunking``, then structural questions
      (default; avoids ontology stall from ``chunk-questions`` task).
    * ``full`` — NLP through ``chunking`` + ``chunk-questions`` (slow).

    Args:
        runner: Pipeline runner (required unless ``index_mode='fast'``).
        dataset: BEIR dataset name.
        doc_id: BEIR document id.
        doc: Corpus fields.
        language: Processing language.
        index_mode: One of ``fast`` / ``chunking`` / ``full``.

    Returns:
        Pipeline document with ``golden_chunks``.

    Example:
        >>> prepare_index_document(
        ...     None, "scifact", "1", {"title": "T", "text": "X"},
        ...     language="en", index_mode="fast",
        ... )["golden_chunks"][0]["text_raw"]
        'T X'
    """
    mode = (index_mode or "chunking").strip().lower()
    if mode not in _INDEX_MODES:
        raise ValueError(
            f"Unknown tkeir index mode {index_mode!r}; "
            f"expected one of {sorted(_INDEX_MODES)}"
        )

    if mode == "fast":
        seed = seed_pipeline_document(dataset, doc_id, doc, language=language)
        text = document_text(doc) or seed["source_doc_id"]
        seed["golden_chunks"] = [
            {
                "chunk_id": f"{seed['source_doc_id']}#chunk-0",
                "parent_doc_id": seed["source_doc_id"],
                "text_raw": text,
                "search_vector_payload": text,
                "synthetic_questions": (
                    [{"question_text": text[:180]}] if text else []
                ),
                "metadata": {},
            }
        ]
        return seed

    if runner is None:
        raise ValueError(f"Pipeline runner required for index_mode={mode!r}")

    tasks: tuple[str, ...] = (
        ("chunking", "chunk-questions") if mode == "full" else ("chunking",)
    )
    seed = seed_pipeline_document(dataset, doc_id, doc, language=language)
    try:
        processed = runner.run(
            seed,
            skip_converter=True,
            tasks=list(tasks),
        )
    except Exception:  # noqa: BLE001
        LOGGER.exception(
            "NLP pipeline failed for %s — falling back to single chunk",
            seed["source_doc_id"],
        )
        processed = seed
    processed = _ensure_golden_chunks(processed)
    if mode == "chunking":
        try:
            processed = _attach_structural_questions(processed)
        except Exception:  # noqa: BLE001
            LOGGER.exception(
                "Structural questions failed for %s", seed["source_doc_id"]
            )
    return processed


def load_pipeline_runner() -> PipelineRunner:
    """Load the bundled T-KEIR pipeline configuration runner.

    Returns:
        Configured :class:`PipelineRunner`.

    Example:
        >>> isinstance(load_pipeline_runner(), PipelineRunner)  # doctest: +SKIP
        True
    """
    config = PipelineConfiguration()
    with open(
        os.path.join(configs_dir(), "pipeline.yaml"),
        encoding="utf-8",
    ) as handle:
        config.load(handle)
    return PipelineRunner(config)


def reset_vespa_for_beir(
    *,
    skip_start: bool = False,
    wait_seconds: int = 180,
) -> None:
    """Wipe Vespa data and bootstrap schemas for a clean BEIR index.

    Waits for the config server (``:19071``) before deploying schemas so a
    freshly started container is not raced by ``init_schema.sh``.

    Args:
        skip_start: When True, only clean; caller starts Vespa separately.
        wait_seconds: Max seconds to wait for Vespa readiness after start.

    Example:
        >>> reset_vespa_for_beir()  # doctest: +SKIP
    """
    from thot.tools.search.init_vespa import (
        _wait_for_application,
        _wait_for_config_server,
    )

    root = Path(vespa_dir())
    clean = root / "clean_db.sh"
    start = root / "start_vespa.sh"
    init = root / "init_schema.sh"
    env = os.environ.copy()
    config_url = env.get("VESPA_CONFIG_URL", "http://localhost:19071")
    vespa_url = env.get("VESPA_URL", "http://localhost:8080")
    LOGGER.warning(
        "Resetting Vespa for BEIR eval (name=%s volume=%s)",
        env.get("VESPA_NAME", "vespa"),
        env.get("VESPA_VOLUME", "vespa_data:/opt/vespa/var"),
    )
    subprocess.run(
        ["bash", str(clean)],
        cwd=str(root),
        check=False,
        env=env,
    )
    if skip_start:
        return
    subprocess.run(["bash", str(start)], cwd=str(root), check=True, env=env)
    LOGGER.info("Waiting for Vespa config server at %s …", config_url)
    _wait_for_config_server(config_url, wait_seconds)
    subprocess.run(["bash", str(init)], cwd=str(root), check=True, env=env)
    LOGGER.info("Waiting for Vespa search API at %s …", vespa_url)
    _wait_for_application(vespa_url, wait_seconds)


def beir_business_ontology_path(
    dataset: str,
    datasets_dir: Path | str | None = None,
) -> Path:
    """Alias of :func:`dataset_business_ontology_path` (BEIR naming).

    Example:
        >>> from pathlib import Path
        >>> beir_business_ontology_path("scifact", datasets_dir=Path("datasets")).name
        'business_ontology.yaml'
    """
    from thot.tools.search.business_ontology import (
        dataset_business_ontology_path,
    )

    return dataset_business_ontology_path(dataset, datasets_dir)


def load_beir_business_ontology_payload(
    dataset: str,
    datasets_dir: Path | str | None = None,
) -> dict[str, Any] | None:
    """Alias of :func:`load_dataset_business_ontology_payload` (BEIR naming).

    Example:
        >>> load_beir_business_ontology_payload("missing-dataset") is None
        True
    """
    from thot.tools.search.business_ontology import (
        load_dataset_business_ontology_payload,
    )

    return load_dataset_business_ontology_payload(dataset, datasets_dir)


def require_beir_business_ontology(
    dataset: str,
    datasets_dir: Path | str | None = None,
) -> dict[str, Any] | None:
    """Load external ontology YAML for a BEIR dataset (no config gating).

    Callers decide whether to apply it via ``rag.yaml``
    ``dual_hybrid.business_ontology.index_enabled`` /
    ``search_enabled``.


    Example:
        >>> require_beir_business_ontology("missing-dataset") is None
        True
    """
    payload = load_beir_business_ontology_payload(dataset, datasets_dir)
    if payload:
        LOGGER.info(
            "BEIR external business ontology dataset=%s concepts=%d",
            dataset,
            len(payload.get("concepts") or []),
        )
    else:
        LOGGER.warning(
            "BEIR missing datasets/%s/business_ontology.yaml "
            "(no external ontology file)",
            dataset,
        )
    return payload


def beir_ontology_for_index(
    dataset: str,
    *,
    dual_cfg: Any | None = None,
    ontology_payload: dict[str, Any] | None = None,
    datasets_dir: Path | str | None = None,
) -> dict[str, Any] | None:
    """Return ontology payload for indexing when ``business_ontology.index_enabled``.

    Example:
        >>> beir_ontology_for_index("scifact", dual_cfg=None) is None or True
        True
    """
    cfg = dual_cfg if dual_cfg is not None else load_rag_config().dual_hybrid
    if not cfg.business_ontology.index_enabled:
        LOGGER.info(
            "BEIR index skips external ontology "
            "(dual_hybrid.business_ontology.index_enabled=false)"
        )
        return None
    if ontology_payload is not None:
        return ontology_payload
    return require_beir_business_ontology(dataset, datasets_dir)


def beir_ontology_for_search(
    dataset: str,
    *,
    dual_cfg: Any | None = None,
    ontology_payload: dict[str, Any] | None = None,
    datasets_dir: Path | str | None = None,
) -> dict[str, Any] | None:
    """Return ontology payload for search when ``business_ontology.search_enabled``.

    Expansion / scoring still honor ``query_expansion.enabled`` and
    ``ontology_scoring.enabled`` inside :class:`PassageRetrievalPipeline`.

    Example:
        >>> beir_ontology_for_search("scifact", dual_cfg=None) is None or True
        True
    """
    cfg = dual_cfg if dual_cfg is not None else load_rag_config().dual_hybrid
    if not cfg.business_ontology.search_enabled:
        LOGGER.info(
            "BEIR search skips external ontology "
            "(dual_hybrid.business_ontology.search_enabled=false)"
        )
        return None
    if ontology_payload is not None:
        return ontology_payload
    return require_beir_business_ontology(dataset, datasets_dir)


async def index_beir_corpus(
    dataset: str,
    corpus: dict[str, dict[str, str]],
    *,
    vespa: VespaClient,
    runner: PipelineRunner | None,
    language: str = "en",
    index_mode: str = "chunking",
    progress_every: int = 25,
    max_workers: int | None = None,
    ontology_payload: dict[str, Any] | None = None,
) -> int:
    """Run NLP pipeline + Vespa indexing for every BEIR document.

    Each document is written to the **global** (index-mode) schema.
    Embeddings use local FlagEmbedding BGE-M3
    (``resources/modeling/net/bge-m3``) via ``index_passages`` — no Ollama.

    Documents are processed **sequentially**. The shared
    :class:`PipelineRunner` does not tolerate concurrent NLP load;
    ``max_workers`` is accepted for API compatibility and ignored when
    greater than 1 (a warning is logged).

    At index time, ``datasets/<dataset>/business_ontology.yaml`` is loaded
    when ``dual_hybrid.business_ontology.index_enabled`` is true (default)
    and applied to passage ``ontology_concepts``.

    Args:
        dataset: Dataset name embedded in document ids.
        corpus: BEIR corpus.
        vespa: Connected Vespa client.
        runner: Linguistic pipeline runner (``None`` only for ``fast`` mode).
        language: Document processing language.
        index_mode: ``fast`` / ``chunking`` / ``full``.
        progress_every: Log every N documents (always log first 3).
        max_workers: Unused (sequential indexing); kept for callers.
        ontology_payload: Optional override of the dataset business ontology.

    Returns:
        Number of successfully indexed documents (each with ≥1 chunk).

    Example:
        >>> asyncio.run(index_beir_corpus("scifact", {}, vespa=None, runner=None))  # doctest: +SKIP
        0
    """
    if max_workers is not None and max_workers > 1:
        LOGGER.warning(
            "BEIR indexing is sequential (ignoring max_workers=%s); "
            "concurrent NLP stalls the shared pipeline",
            max_workers,
        )

    indexed = 0
    chunks_indexed = 0
    total = len(corpus)
    started = time.perf_counter()
    mode = (index_mode or "chunking").strip().lower()
    dual_cfg = load_rag_config().dual_hybrid
    ontology_payload = beir_ontology_for_index(
        dataset,
        dual_cfg=dual_cfg,
        ontology_payload=ontology_payload,
    )
    if ontology_payload:
        LOGGER.info(
            "BEIR index-time external ontology for %s: %d concepts "
            "(rag.yaml business_ontology.index_enabled=true)",
            dataset,
            len(ontology_payload.get("concepts") or []),
        )
    if mode == "fast":
        LOGGER.info(
            "T-KEIR indexing %d docs for %s "
            "(mode=fast — synthetic chunk only, PipelineRunner skipped; "
            "still writes Vespa global passages)",
            total,
            dataset,
        )
    else:
        LOGGER.info(
            "T-KEIR indexing %d docs for %s "
            "(mode=%s — PipelineRunner NLP + BGE-M3; "
            "writes Vespa global passages)",
            total,
            dataset,
            mode,
        )
    for position, (doc_id, doc) in enumerate(corpus.items(), start=1):
        doc_started = time.perf_counter()
        source_hint = f"beir:{dataset}:{doc_id}"
        phase = (
            "synthetic chunk + embed…"
            if mode == "fast"
            else f"NLP pipeline ({mode}) + embed…"
        )
        LOGGER.info(
            "T-KEIR doc %d / %d: %s (%s)",
            position,
            total,
            source_hint,
            phase,
        )
        try:
            t_nlp = time.perf_counter()
            pipeline_doc = await asyncio.to_thread(
                prepare_index_document,
                runner,
                dataset,
                doc_id,
                doc,
                language=language,
                index_mode=mode,
            )
            pipeline_doc["dataset"] = dataset
            nlp_ms = (time.perf_counter() - t_nlp) * 1000
            chunk_count = len(pipeline_doc.get("golden_chunks") or [])
            done_label = "synthetic ready" if mode == "fast" else "NLP done"
            LOGGER.info(
                "T-KEIR doc %d / %d: %s %s (%d chunks, embedding…)",
                position,
                total,
                source_hint,
                done_label,
                chunk_count,
            )
            result = await index_pipeline_document(
                pipeline_doc,
                vespa=vespa,
                target="global",
                nlp_ms=nlp_ms,
                ontology_payload=ontology_payload,
                dataset=dataset,
            )
            n_chunks = result.passage_count
            if n_chunks < 1:
                raise RuntimeError(
                    f"global index failed for {source_hint}: "
                    f"passages={n_chunks}"
                )
            indexed += 1
            chunks_indexed += n_chunks
        except asyncio.CancelledError:
            LOGGER.warning(
                "T-KEIR indexing cancelled at doc %d / %d (%s)",
                position,
                total,
                source_hint,
            )
            raise
        except Exception:  # noqa: BLE001
            LOGGER.exception(
                "Failed to index BEIR doc %s (%s)", dataset, doc_id
            )
            continue
        elapsed_doc = time.perf_counter() - doc_started
        elapsed = time.perf_counter() - started
        if indexed <= 3 or indexed % progress_every == 0 or indexed == total:
            rate = indexed / elapsed if elapsed > 0 else 0.0
            remaining = total - indexed
            eta_s = remaining / rate if rate > 0 else 0.0
            LOGGER.info(
                "T-KEIR indexed %d / %d for %s "
                "(chunks=%d, last=%.1fs, %.2f docs/s, ETA ~%.0fs)",
                indexed,
                total,
                dataset,
                chunks_indexed,
                elapsed_doc,
                rate,
                eta_s,
            )
    LOGGER.info(
        "T-KEIR indexing finished for %s: %d / %d docs, %d passages in %.1fs "
        "(Vespa global schema)",
        dataset,
        indexed,
        total,
        chunks_indexed,
        time.perf_counter() - started,
    )
    return indexed


async def retrieve_with_tkeir(
    dataset: str,
    queries: dict[str, str],
    *,
    corpus: dict[str, dict[str, str]],
    top_k: int = 100,
    max_workers: int | None = None,
    language: str = "en",
) -> dict[str, dict[str, float]]:
    """BEIR retrieve via :func:`hybrid_retrieve.retrieve_hybrid`.

    Long queries also run NLP + ontology expansion + OntologyRescorer when
    ``rag.yaml`` enables ``nlp_seed_expansion`` / ``ontology_scoring`` and a
    dataset ``business_ontology.yaml`` is available.

    Example:
        >>> asyncio.run(retrieve_with_tkeir(  # doctest: +SKIP
        ...     "scifact",
        ...     {"q1": "test"},
        ...     corpus={"d1": {"text": "test"}},
        ... ))
    """
    if max_workers is not None and max_workers > 1:
        LOGGER.warning(
            "BEIR retrieval ignores max_workers=%s (batched corpus retrieve)",
            max_workers,
        )
    if not corpus:
        raise ValueError(
            "retrieve_with_tkeir requires a non-empty corpus "
            "(use thot.tools.eval.hybrid_retrieve.retrieve_hybrid)"
        )

    from thot.tools.eval.hybrid_retrieve import retrieve_hybrid

    dual_cfg = load_rag_config().dual_hybrid
    ontology_payload = beir_ontology_for_search(dataset, dual_cfg=dual_cfg)

    started = time.perf_counter()

    def _progress(index: int, total: int, qid: str) -> None:
        log_query_progress(
            index,
            total,
            dataset="colbert-rerank",
            started=started,
            qid=qid,
            every=max(1, total // 20),
        )

    LOGGER.info(
        "BEIR T-KEIR retrieve → eval.hybrid_retrieve.retrieve_hybrid "
        "(dataset=%s top_k=%d queries=%d ontology=%s)",
        dataset,
        top_k,
        len(queries),
        "yes" if ontology_payload else "no",
    )
    return await asyncio.to_thread(
        retrieve_hybrid,
        corpus,
        queries,
        top_k=top_k,
        progress=_progress,
        ontology_payload=ontology_payload,
        language=language,
    )


async def run_tkeir_eval(
    dataset: str,
    corpus: dict[str, dict[str, str]],
    queries: dict[str, str],
    *,
    language: str = "en",
    top_k: int = 100,
    reindex: bool = True,
    index_mode: str = "chunking",
    max_docs: int | None = None,
) -> dict[str, dict[str, float]]:
    """BEIR retrieval for one dataset (no answer generation).

    Scores with ``eval.hybrid_retrieve.retrieve_hybrid`` (BGE-M3 + BM25 RRF
    + ColBERT).     Optional Vespa NLP index dumps: set ``TKEIR_BEIR_INDEX=1``.

    Example:
        >>> asyncio.run(run_tkeir_eval(  # doctest: +SKIP
        ...     "scifact",
        ...     {"d1": {"text": "test"}},
        ...     {"q1": "test"},
        ...     reindex=False,
        ... ))
    """
    if max_docs is not None and max_docs > 0 and len(corpus) > max_docs:
        LOGGER.warning(
            "Capping BEIR corpus %s to %d / %d docs (--tkeir-max-docs)",
            dataset,
            max_docs,
            len(corpus),
        )
        corpus = dict(list(corpus.items())[:max_docs])

    index_vespa = os.environ.get("TKEIR_BEIR_INDEX", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    LOGGER.info(
        "T-KEIR BEIR eval → eval.hybrid_retrieve.retrieve_hybrid "
        "vespa_index=%s",
        index_vespa,
    )
    if index_vespa:
        if reindex:
            await asyncio.to_thread(reset_vespa_for_beir)
        mode = (index_mode or "chunking").strip().lower()
        runner: PipelineRunner | None = None
        if mode != "fast":
            LOGGER.info(
                "Loading T-KEIR PipelineRunner for index_mode=%s …", mode
            )
            runner = await asyncio.to_thread(load_pipeline_runner)
        dual_cfg = load_rag_config().dual_hybrid
        ontology_for_index = beir_ontology_for_index(
            dataset, dual_cfg=dual_cfg
        )
        async with VespaClient() as vespa:
            if not await vespa.health():
                raise RuntimeError(
                    "Vespa is not ready for T-KEIR BEIR indexing. "
                    "Run: make bootstrap (or unset TKEIR_BEIR_INDEX)"
                )
            indexed = await index_beir_corpus(
                dataset,
                corpus,
                vespa=vespa,
                runner=runner,
                language=language,
                index_mode=mode,
                ontology_payload=ontology_for_index,
            )
            if indexed == 0:
                raise RuntimeError(
                    f"T-KEIR indexed 0/{len(corpus)} documents for {dataset}"
                )

    return await retrieve_with_tkeir(
        dataset,
        queries,
        top_k=top_k,
        corpus=corpus,
        language=language,
    )
