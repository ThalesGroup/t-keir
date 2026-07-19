"""T-KEIR full NLP pipeline + Vespa hybrid retrieval for BEIR evaluation.

Indexes each BEIR document through :class:`PipelineRunner` (tokenizer →
chunking → structural question projections), embeds with the production
provider, retrieves via :class:`QueryAnalyzerTask` (adaptive rank profile),
and maps chunk hits back to BEIR document ids.

**Retrieval only:** answer generation (``UnifiedLLMWrapper.generate`` / RAG
prompting) is never invoked. LLM access is restricted to embeddings via
:class:`RetrievalEmbeddingClient`.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import subprocess
from pathlib import Path
from typing import Any

from thot.core.LlmWrapper import UnifiedLLMWrapper
from thot.core.TkeirPaths import configs_dir, vespa_dir
from thot.tasks.pipeline.PipelineConfiguration import PipelineConfiguration
from thot.tasks.pipeline.PipelineRunner import PipelineRunner
from thot.tools.search.index_documents import index_pipeline_document
from thot.tools.search.query_analyzer import QueryAnalyzerTask
from thot.tools.search.rag_config import RagSearchConfig, load_rag_config
from thot.tools.search.rerank import rerank_vespa_children
from thot.tools.search.vespa_client import VespaClient

LOGGER = logging.getLogger(__name__)

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


class RetrievalEmbeddingClient:
    """Embedding-only facade that forbids LLM answer generation.

    Wraps :class:`UnifiedLLMWrapper` so BEIR / IR evaluation can index and
    query without calling ``generate``.

    Args:
        llm: Underlying wrapper used solely for ``embed`` / ``embed_batch``.
    """

    def __init__(self, llm: UnifiedLLMWrapper) -> None:
        """Bind the embedding provider.

        Example:
            >>> RetrievalEmbeddingClient(UnifiedLLMWrapper())  # doctest: +SKIP
        """
        self._llm = llm

    async def embed(self, text: str) -> list[float]:
        """Embed one text (retrieval indexing / query vectors).

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(RetrievalEmbeddingClient.embed)
            True
        """
        return await self._llm.embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(RetrievalEmbeddingClient.embed_batch)
            True
        """
        return await self._llm.embed_batch(texts)

    async def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_n: int | None = None,
        strategy: str | None = None,
    ) -> list[dict[str, Any]]:
        """Rerank candidates (allowed for IR eval; not answer generation).

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(RetrievalEmbeddingClient.rerank)
            True
        """
        return await self._llm.rerank(
            query,
            documents,
            top_n=top_n,
            strategy=strategy,
        )

    async def generate(self, prompt: str, *, temperature: float = 0.1) -> str:
        """Hard-fail: IR evaluation must not run T-KEIR answer generation.

        Raises:
            RuntimeError: Always — generation is disabled for retrieval eval.

        Example:
            >>> import asyncio
            >>> asyncio.run(RetrievalEmbeddingClient(None).generate("x"))  # doctest: +SKIP
        """
        del prompt, temperature
        raise RuntimeError(
            "T-KEIR IR evaluation is retrieval-only: "
            "answer generation (LLM.generate) is disabled"
        )

    async def verify_provider(self, **kwargs: Any) -> None:
        """Delegate provider health check to the underlying wrapper.

        Example:
            >>> asyncio.run(RetrievalEmbeddingClient(UnifiedLLMWrapper()).verify_provider())  # doctest: +SKIP
        """
        await self._llm.verify_provider(**kwargs)


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


def parse_beir_doc_id(value: str, dataset: str) -> str | None:
    """Extract a BEIR document id from a ``source_doc_id`` / ``chunk_id``.

    Chunk ids may look like ``beir:scifact:42#chunk-0-abcd``; only the
    parent BEIR id before ``#`` is returned.

    Args:
        value: Indexed id string.
        dataset: Expected dataset name.

    Returns:
        BEIR doc id, or ``None`` when the value is not for ``dataset``.

    Example:
        >>> parse_beir_doc_id("beir:scifact:42#chunk-0-aa", "scifact")
        '42'
        >>> parse_beir_doc_id("beir:fiqa:9", "scifact") is None
        True
    """
    prefix = f"{BEIR_ID_PREFIX}:{dataset}:"
    if not value.startswith(prefix):
        return None
    remainder = value[len(prefix) :]
    return remainder.split("#", 1)[0]


def document_text(doc: dict[str, str]) -> str:
    """Join BEIR title and text for indexing.

    Args:
        doc: Corpus entry.

    Returns:
        Combined text.

    Example:
        >>> document_text({"title": "A", "text": "B"})
        'A B'
    """
    title = (doc.get("title") or "").strip()
    body = (doc.get("text") or "").strip()
    if title and body:
        return f"{title} {body}"
    return title or body


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


# Backward-compatible name used in older docs/call sites.
def run_document_pipeline(
    runner: PipelineRunner,
    dataset: str,
    doc_id: str,
    doc: dict[str, str],
    *,
    language: str,
    tasks: tuple[str, ...] = _INDEX_PIPELINE_TASKS,
) -> dict[str, Any]:
    """Run document NLP for indexing (alias of :func:`prepare_index_document`).

    Example:
        >>> run_document_pipeline(None, "scifact", "1", {}, language="en")  # doctest: +SKIP
    """
    mode = "full" if "chunk-questions" in tasks else "chunking"
    return prepare_index_document(
        runner,
        dataset,
        doc_id,
        doc,
        language=language,
        index_mode=mode,
    )


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


def tkeir_search_config(*, hits: int) -> RagSearchConfig:
    """Return RAG search settings for BEIR evaluation (adaptive ranking).

    Args:
        hits: Number of Vespa hits to request per query.

    Returns:
        Frozen :class:`RagSearchConfig` with ``ranking_profile='auto'``.

    Example:
        >>> tkeir_search_config(hits=100).hits
        100
    """
    base = load_rag_config().search
    first_stage_hits = hits
    if base.rerank.enabled:
        first_stage_hits = max(hits, base.rerank.candidates)
    return RagSearchConfig(
        enabled=True,
        use_chunk_embedding=base.use_chunk_embedding,
        use_question_embedding=base.use_question_embedding,
        use_text_raw=base.use_text_raw,
        use_parent_content=base.use_parent_content,
        use_parent_title=base.use_parent_title,
        use_ner=base.use_ner,
        use_svo=base.use_svo,
        use_keywords=base.use_keywords,
        use_lemmas=base.use_lemmas,
        ranking_profile="auto",
        hits=first_stage_hits,
        max_yql_terms=max(base.max_yql_terms, 48),
        weight_chunk_embedding=base.weight_chunk_embedding,
        weight_question_embedding=base.weight_question_embedding,
        weight_text_raw_bm25=base.weight_text_raw_bm25,
        weight_parent_content_bm25=base.weight_parent_content_bm25,
        weight_parent_title_bm25=base.weight_parent_title_bm25,
        rerank=base.rerank,
    )


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


async def index_beir_corpus(
    dataset: str,
    corpus: dict[str, dict[str, str]],
    *,
    vespa: VespaClient,
    llm: RetrievalEmbeddingClient | UnifiedLLMWrapper,
    runner: PipelineRunner | None,
    language: str = "en",
    index_mode: str = "chunking",
    progress_every: int = 25,
    max_workers: int | None = None,
) -> int:
    """Run NLP pipeline + Vespa indexing for every BEIR document.

    Documents are processed **sequentially**. The shared
    :class:`PipelineRunner` and local embedding providers (Ollama) do not
    tolerate concurrent NLP/embed load; parallel workers previously stalled
    long BEIR runs. ``max_workers`` is accepted for API compatibility and
    ignored when greater than 1 (a warning is logged).

    Args:
        dataset: Dataset name embedded in document ids.
        corpus: BEIR corpus.
        vespa: Connected Vespa client.
        llm: Embedding-only client (or wrapper exposing ``embed``).
        runner: Linguistic pipeline runner (``None`` only for ``fast`` mode).
        language: Document processing language.
        index_mode: ``fast`` / ``chunking`` / ``full``.
        progress_every: Log every N documents (always log first 3).
        max_workers: Unused (sequential indexing); kept for callers.

    Returns:
        Number of successfully indexed documents.

    Example:
        >>> asyncio.run(index_beir_corpus("scifact", {}, vespa=None, llm=None, runner=None))  # doctest: +SKIP
        0
    """
    import time

    if max_workers is not None and max_workers > 1:
        LOGGER.warning(
            "BEIR indexing is sequential (ignoring max_workers=%s); "
            "concurrent NLP/embed stalls Ollama and the shared pipeline",
            max_workers,
        )

    indexed = 0
    total = len(corpus)
    started = time.perf_counter()
    LOGGER.info(
        "T-KEIR indexing %d docs for %s (mode=%s, sequential, retrieval-only)",
        total,
        dataset,
        index_mode,
    )
    for position, (doc_id, doc) in enumerate(corpus.items(), start=1):
        doc_started = time.perf_counter()
        source_hint = f"beir:{dataset}:{doc_id}"
        LOGGER.info(
            "T-KEIR doc %d / %d: %s (NLP + embed…)",
            position,
            total,
            source_hint,
        )
        try:
            pipeline_doc = await asyncio.to_thread(
                prepare_index_document,
                runner,
                dataset,
                doc_id,
                doc,
                language=language,
                index_mode=index_mode,
            )
            chunk_count = len(pipeline_doc.get("golden_chunks") or [])
            LOGGER.info(
                "T-KEIR doc %d / %d: %s NLP done (%d chunks, embedding…)",
                position,
                total,
                source_hint,
                chunk_count,
            )
            await index_pipeline_document(pipeline_doc, vespa=vespa, llm=llm)
            indexed += 1
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
                "(last=%.1fs, %.2f docs/s, ETA ~%.0fs)",
                indexed,
                total,
                dataset,
                elapsed_doc,
                rate,
                eta_s,
            )
    LOGGER.info(
        "T-KEIR indexing finished for %s: %d / %d in %.1fs",
        dataset,
        indexed,
        total,
        time.perf_counter() - started,
    )
    return indexed


def _aggregate_hits_to_beir(
    search_response: dict[str, Any],
    dataset: str,
) -> dict[str, float]:
    """Map Vespa chunk hits to BEIR document ids with multi-chunk boost.

    Score = max(chunk relevance) + log1p(hit_count) * small bonus so
    documents with several matching chunks rise without language heuristics.

    Args:
        search_response: Raw Vespa ``/search/`` JSON.
        dataset: Active dataset (filters foreign hits).

    Returns:
        Mapping ``beir_doc_id → relevance``.

    Example:
        >>> scores = _aggregate_hits_to_beir(
        ...     {"root": {"children": [
        ...         {"fields": {"chunk_id": "beir:scifact:9#chunk-0-a"}, "relevance": 0.8}
        ...     ]}},
        ...     "scifact",
        ... )
        >>> round(scores["9"], 6)
        0.834657
    """
    best: dict[str, float] = {}
    counts: dict[str, int] = {}
    children = (search_response.get("root") or {}).get("children") or []
    for child in children:
        fields = child.get("fields") or {}
        chunk_id = str(fields.get("chunk_id") or "")
        beir_id = parse_beir_doc_id(chunk_id, dataset)
        if beir_id is None:
            continue
        relevance = child.get("relevance")
        if relevance is None:
            continue
        score = float(relevance)
        previous = best.get(beir_id)
        if previous is None or score > previous:
            best[beir_id] = score
        counts[beir_id] = counts.get(beir_id, 0) + 1
    # Mild multi-evidence boost (programmatic, scale-free).
    for beir_id, score in list(best.items()):
        best[beir_id] = score + 0.05 * math.log1p(counts.get(beir_id, 1))
    return best


async def retrieve_with_tkeir(
    dataset: str,
    queries: dict[str, str],
    *,
    vespa: VespaClient,
    llm: RetrievalEmbeddingClient | UnifiedLLMWrapper,
    runner: PipelineRunner,
    language: str = "en",
    top_k: int = 100,
    max_workers: int | None = None,
) -> dict[str, dict[str, float]]:
    """Run T-KEIR QueryAnalyzer + Vespa hybrid search for every query.

    Retrieval only: NLP query analysis, embeddings, and Vespa search.
    Queries run **sequentially** (shared pipeline + embedding provider).
    ``max_workers`` is accepted for API compatibility; values > 1 log a
    warning and are ignored.

    Args:
        dataset: BEIR dataset name (for hit id filtering).
        queries: Query id → text.
        vespa: Vespa client.
        llm: Embedding-only client used by the analyzer.
        runner: Linguistic pipeline runner for query analysis.
        language: Pipeline language code.
        top_k: Hits requested from Vespa.
        max_workers: Unused (sequential retrieval); kept for callers.

    Returns:
        BEIR results dict ``{qid: {doc_id: score}}``.

    Example:
        >>> asyncio.run(retrieve_with_tkeir("scifact", {}, vespa=None, llm=None, runner=None))  # doctest: +SKIP
        {}
    """
    if max_workers is not None and max_workers > 1:
        LOGGER.warning(
            "BEIR retrieval is sequential (ignoring max_workers=%s)",
            max_workers,
        )

    config = tkeir_search_config(hits=top_k)
    analyzer = QueryAnalyzerTask(
        runner,
        llm,
        config,
        embedding_dim=vespa.config.embedding_dim,
        timeout_seconds=vespa.config.timeout_seconds,
        user_space=vespa.config.user_space,
    )
    rerank_cfg = config.rerank
    results: dict[str, dict[str, float]] = {}
    total = len(queries)
    for index, (qid, qtext) in enumerate(queries.items(), start=1):
        try:
            analyzed = await analyzer.process(
                qtext, language=language, hits=config.hits
            )
            response = await vespa.search(analyzed["payload"])
            if rerank_cfg.enabled and hasattr(llm, "rerank"):
                root = dict(response.get("root") or {})
                children = list(root.get("children") or [])
                candidate_n = min(len(children), rerank_cfg.candidates)
                reranked = await rerank_vespa_children(
                    llm,
                    qtext,
                    children[:candidate_n],
                    top_n=top_k,
                    strategy=rerank_cfg.strategy,
                )
                root["children"] = reranked
                response = {**response, "root": root}
            results[qid] = _aggregate_hits_to_beir(response, dataset)
        except Exception:  # noqa: BLE001
            LOGGER.exception(
                "T-KEIR retrieval failed for query %s on %s", qid, dataset
            )
            results[qid] = {}
        if index % 50 == 0 or index == total:
            LOGGER.info(
                "T-KEIR retrieved %d / %d queries for %s",
                index,
                total,
                dataset,
            )
    return results


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
    """Index + adaptive hybrid retrieve for one BEIR dataset (retrieval only).

    **Does not run T-KEIR answer generation.** NLP indexing, embeddings,
    query analysis, and Vespa hybrid search only.

    Args:
        dataset: BEIR dataset name.
        corpus: Documents to index.
        queries: Test queries.
        language: Pipeline language for docs and queries.
        top_k: Retrieval cut-off.
        reindex: When True, wipe Vespa and re-deploy before indexing.
        index_mode: ``fast`` / ``chunking`` (default) / ``full``.
        max_docs: Optional corpus cap for smoke tests (None = all).

    Returns:
        BEIR-style retrieval results.

    Example:
        >>> asyncio.run(run_tkeir_eval("scifact", {}, {}))  # doctest: +SKIP
        {}
    """
    if max_docs is not None and max_docs > 0 and len(corpus) > max_docs:
        LOGGER.warning(
            "Capping BEIR corpus %s to %d / %d docs (--tkeir-max-docs)",
            dataset,
            max_docs,
            len(corpus),
        )
        corpus = dict(list(corpus.items())[:max_docs])

    if reindex:
        await asyncio.to_thread(reset_vespa_for_beir)

    mode = (index_mode or "chunking").strip().lower()
    runner: PipelineRunner | None = None
    if mode != "fast":
        LOGGER.info("Loading T-KEIR PipelineRunner for index_mode=%s …", mode)
        runner = await asyncio.to_thread(load_pipeline_runner)
    LOGGER.info(
        "T-KEIR BEIR eval retrieval-only index_mode=%s "
        "(answer generation disabled)",
        mode,
    )
    async with UnifiedLLMWrapper() as llm_full, VespaClient() as vespa:
        llm = RetrievalEmbeddingClient(llm_full)
        await llm.verify_provider(
            pull_missing=True,
            include_reranker=load_rag_config().search.rerank.enabled,
        )
        if not await vespa.health():
            raise RuntimeError(
                "Vespa is not ready for T-KEIR BEIR evaluation. "
                "Run: make bootstrap"
            )
        indexed = await index_beir_corpus(
            dataset,
            corpus,
            vespa=vespa,
            llm=llm,
            runner=runner,
            language=language,
            index_mode=mode,
        )
        if indexed == 0:
            raise RuntimeError(
                f"T-KEIR indexed 0/{len(corpus)} documents for {dataset}"
            )
        if runner is None:
            runner = await asyncio.to_thread(load_pipeline_runner)
        return await retrieve_with_tkeir(
            dataset,
            queries,
            vespa=vespa,
            llm=llm,
            runner=runner,
            language=language,
            top_k=top_k,
        )


def corpus_to_pipeline_document(
    dataset: str,
    doc_id: str,
    doc: dict[str, str],
    language: str = "en",
) -> dict[str, Any]:
    """Compatibility wrapper around :func:`seed_pipeline_document`.

    Example:
        >>> corpus_to_pipeline_document("scifact", "1", {"title": "T", "text": "X"})["source_doc_id"]
        'beir:scifact:1'
    """
    return seed_pipeline_document(dataset, doc_id, doc, language=language)
