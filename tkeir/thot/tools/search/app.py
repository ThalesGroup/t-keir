# -*- coding: utf-8 -*-
"""FastAPI RAG application over Vespa 2-level document/chunk retrieval."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from thot import __version__ as TKEIR_VERSION
from thot.core.ThotLogger import ThotLogger
from thot.core.TkeirPaths import configs_dir, rag_prompts_path
from thot.tasks.pipeline.PipelineConfiguration import PipelineConfiguration
from thot.tasks.pipeline.PipelineRunner import PipelineRunner
from thot.core.LlmWrapper import UnifiedLLMWrapper
from thot.tools.search.ontology_utils import (
    build_hmi_ontology,
    extract_focus_passages,
    merge_rdf_graphs,
    prioritize_chunks_by_query_match,
    summarize_graph_for_prompt,
    truncate_for_prompt,
)
from thot.tools.search.query_refiner import refine_search_query_text
from thot.tools.search.rag_config import RagConfig, load_rag_config
from thot.tools.search.rag_report import (
    apply_chunk_evidence_fallback,
    assemble_report_markdown,
    build_fallback_detailed_report,
    extract_highlight_labels,
    is_unavailable_short_answer,
    parse_structured_generation,
    query_highlight_terms,
)
from thot.tools.search.vespa_client import VespaClient

LOGGER = logging.getLogger(__name__)
PROMPTS_PATH = rag_prompts_path()

_DEFAULT_UNAVAILABLE_ANSWERS = {
    "en": "The information is not available.",
    "fr": "L'information n'est pas disponible.",
}


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    language: str = Field(default="en", pattern="^(en|fr)$")
    hits: int = Field(default=20, ge=1, le=100)


class RetrievedChunk(BaseModel):
    chunk_id: str
    text_raw: str
    parent_doc_id: str
    relevance: float | None = None


class SemanticEntity(BaseModel):
    label: str
    type: str
    chunk_ids: list[str] = Field(default_factory=list)


class SemanticKeyword(BaseModel):
    label: str
    chunk_ids: list[str] = Field(default_factory=list)


class FusedOntology(BaseModel):
    entities: list[SemanticEntity]
    keywords: list[SemanticKeyword]
    json_ld: str = ""


class QueryResponse(BaseModel):
    answer: str
    report_markdown: str
    highlight_entities: list[str] = Field(default_factory=list)
    highlight_keywords: list[str] = Field(default_factory=list)
    highlight_query_terms: list[str] = Field(default_factory=list)
    used_chunk_evidence: bool = False
    answer_unavailable: bool = False
    chunks: list[RetrievedChunk]
    ontology: FusedOntology
    vespa_hits: int


class AppState:
    def __init__(self) -> None:
        """Initialize empty RAG application state.

        Example:
            >>> from thot.tools.search.app import AppState
            >>> AppState().prompts
            {}
        """
        self.llm: UnifiedLLMWrapper | None = None
        self.vespa: VespaClient | None = None
        self.pipeline_runners: dict[str, PipelineRunner] = {}
        self.prompts: dict[str, Any] = {}
        self.rag_config: RagConfig = load_rag_config()


def _load_prompts() -> dict[str, Any]:
    """Load RAG prompt templates from the bundled YAML file.

    Example:
        >>> prompts = _load_prompts()
        >>> "en" in prompts
        True
    """
    with open(PROMPTS_PATH, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _language_prompt_cfg(
    prompts: dict[str, Any], language: str
) -> dict[str, Any]:
    """Return the prompt block for a language with English fallback.

    Example:
        >>> _language_prompt_cfg({"en": {"user": "hi"}}, "fr")["user"]
        'hi'
    """
    return prompts.get(language) or prompts["en"]


def _unavailable_answer(prompt_cfg: dict[str, Any], language: str) -> str:
    """Return the configured unavailable answer for a language.

    Args:
        prompt_cfg: Language block from ``rag-prompts.yaml``.
        language: Request language code (``en`` or ``fr``).

    Returns:
        Localized fallback when retrieval cannot answer.

    Example:
        >>> from thot.tools.search.app import _unavailable_answer
        >>> _unavailable_answer({"unavailable_answer": "N/A"}, "en")
        'N/A'
    """
    configured = prompt_cfg.get("unavailable_answer")
    if configured:
        return str(configured).strip()
    return _DEFAULT_UNAVAILABLE_ANSWERS.get(
        language,
        _DEFAULT_UNAVAILABLE_ANSWERS["en"],
    )


def _no_chunks_message(prompt_cfg: dict[str, Any]) -> str:
    """Return the message used when no chunks are retrieved.

    Args:
        prompt_cfg: Language block from ``rag-prompts.yaml``.

    Returns:
        Prompt fragment for empty retrieval.

    Example:
        >>> from thot.tools.search.app import _no_chunks_message
        >>> _no_chunks_message({})
        'No relevant chunks retrieved.'
    """
    configured = prompt_cfg.get("no_chunks_message")
    if configured:
        return str(configured).strip()
    return "No relevant chunks retrieved."


_DEFAULT_MAX_TRIPLES_FOR_PROMPT = 25
_DEFAULT_MAX_CHARS_PER_CHUNK = 800
_DEFAULT_MAX_CHUNKS_FOR_PROMPT = 5
_DEFAULT_MAX_FOCUS_PASSAGES = 4
_PIPELINE_PRELOAD_LANGUAGES = ("en", "fr")


def _log_rag_step(step: str, start: float, **details: Any) -> None:
    """Log elapsed time for one RAG pipeline step.

    Example:
        >>> import time
        >>> from thot.tools.search.app import _log_rag_step
        >>> started = time.perf_counter()
        >>> _log_rag_step("query-generation", started, query="hello")  # doctest: +SKIP
    """
    elapsed = time.perf_counter() - start
    suffix = " ".join(f"{key}={value}" for key, value in details.items())
    message = f"RAG step {step} elapsed={elapsed:.3f}s"
    if suffix:
        message = f"{message} {suffix}"
    ThotLogger.info(message)


def _build_generation_prompts(
    prompt_cfg: dict[str, Any],
    *,
    fused_summary: str,
    focus_passages: str,
    chunk_excerpts: str,
    query_text: str,
    unavailable_answer: str,
) -> tuple[str, str]:
    """Build system and user prompts for answer generation.

    Example:
        >>> cfg = {"user": "Q:{query_text} F:{focus_passages}", "system": "S:{unavailable_answer}"}
        >>> _build_generation_prompts(cfg, fused_summary="", focus_passages="p", chunk_excerpts="", query_text="Hi", unavailable_answer="N/A")
        ('S:N/A', 'Q:Hi F:p')
    """
    format_kwargs = {
        "fused_graph_triples_or_summary": fused_summary,
        "focus_passages": focus_passages,
        "chunk_excerpts": chunk_excerpts,
        "query_text": query_text,
        "unavailable_answer": unavailable_answer,
    }
    user_prompt = prompt_cfg["user"].format(**format_kwargs)
    system_prompt = prompt_cfg.get("system", "").format(**format_kwargs)
    return system_prompt.strip(), user_prompt.strip()


def _format_chunk_excerpts(
    chunks: list[RetrievedChunk],
    *,
    empty_message: str,
    max_chars_per_chunk: int = 1200,
    max_chunks: int = 8,
) -> str:
    """Format retrieved chunks for the LLM user prompt.

    Args:
        chunks: Ranked chunks from Vespa.
        empty_message: Text when ``chunks`` is empty.
        max_chars_per_chunk: Maximum characters kept per chunk body.
        max_chunks: Maximum number of chunks included in the prompt.

    Returns:
        Delimited excerpt block for prompt injection.

    Example:
        >>> from thot.tools.search.app import RetrievedChunk, _format_chunk_excerpts
        >>> chunk = RetrievedChunk(chunk_id="c1", text_raw="Hello world.", parent_doc_id="doc")
        >>> "Hello world." in _format_chunk_excerpts([chunk], empty_message="none")
        True
    """
    blocks: list[str] = []
    for chunk in chunks[:max_chunks]:
        relevance = (
            f"{chunk.relevance:.4f}" if chunk.relevance is not None else "n/a"
        )
        body = truncate_for_prompt(
            chunk.text_raw,
            max_chars=max_chars_per_chunk,
        )
        blocks.append(
            "---\n"
            f"Chunk ID : {chunk.chunk_id}\n"
            f"Relevance : {relevance}\n"
            f"Document Source : {chunk.parent_doc_id}\n"
            f"Contenu : {body}\n"
            "---"
        )
    return "\n".join(blocks) if blocks else empty_message


def _extract_parent_rdf(parent_fields: dict[str, Any]) -> str:
    """Extract JSON-LD graph text from parent Vespa fields.

    Example:
        >>> _extract_parent_rdf({"json_ld": '[{"@id": "http://example.org/a"}]'})
        '[{"@id": "http://example.org/a"}]'
    """
    for key in ("json_ld", "rdf_graph_serialized"):
        value = parent_fields.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


async def _enrich_hits(
    state: AppState,
    parsed_hits: list[tuple[dict[str, Any], float | None]],
) -> tuple[list[RetrievedChunk], list[str]]:
    """Attach parent document metadata to Vespa chunk hits.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(_enrich_hits)
        True
    """
    retrieved_chunks: list[RetrievedChunk] = []
    rdf_payloads: list[str] = []
    parent_cache: dict[str, dict[str, Any]] = {}

    for fields, relevance in parsed_hits:
        chunk_id = str(fields.get("chunk_id") or "")
        text_raw = str(fields.get("text_raw") or "")
        doc_ref = str(fields.get("doc_ref") or "")
        if not chunk_id or not text_raw:
            continue

        parent_fields: dict[str, Any] = {}
        if doc_ref:
            if doc_ref not in parent_cache and state.vespa is not None:
                try:
                    parent_cache[doc_ref] = (
                        await state.vespa.get_document_by_ref(doc_ref)
                    )
                except Exception:
                    LOGGER.warning(
                        "Unable to fetch parent document %s", doc_ref
                    )
                    parent_cache[doc_ref] = {}
            parent_fields = parent_cache.get(doc_ref, {})

        parent_doc_id = str(
            parent_fields.get("source_doc_id") or doc_ref or ""
        )
        retrieved_chunks.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                text_raw=text_raw,
                parent_doc_id=parent_doc_id,
                relevance=relevance,
            )
        )
        rdf_payloads.append(_extract_parent_rdf(parent_fields))

    return retrieved_chunks, rdf_payloads


def _parse_hits(
    search_response: dict[str, Any],
) -> list[tuple[dict[str, Any], float | None]]:
    """Extract field dicts and relevance scores from a Vespa search response.

    Args:
        search_response: Raw JSON from Vespa ``/search/``.

    Returns:
        List of ``(fields, relevance)`` tuples.

    Example:
        >>> from thot.tools.search.app import _parse_hits
        >>> _parse_hits({"root": {"children": [{"fields": {"chunk_id": "c1"}, "relevance": 0.9}]}})
        [({'chunk_id': 'c1'}, 0.9)]
    """
    root = search_response.get("root") or {}
    children = root.get("children") or []
    parsed: list[tuple[dict[str, Any], float | None]] = []
    for child in children:
        fields = child.get("fields") or {}
        relevance = child.get("relevance")
        parsed.append((fields, relevance))
    return parsed


def _load_pipeline_configuration() -> PipelineConfiguration:
    """Load the bundled pipeline configuration.

    Example:
        >>> from thot.tools.search.app import _load_pipeline_configuration
        >>> isinstance(_load_pipeline_configuration(), PipelineConfiguration)
        True
    """
    config = PipelineConfiguration()
    with open(
        os.path.join(configs_dir(), "pipeline.json"),
        encoding="utf-8",
    ) as handle:
        config.load(handle)
    return config


def _load_pipeline_runner() -> PipelineRunner:
    """Load a pipeline runner with the bundled configuration.

    Example:
        >>> from thot.tools.search.app import _load_pipeline_runner
        >>> isinstance(_load_pipeline_runner(), PipelineRunner)
        True
    """
    return PipelineRunner(_load_pipeline_configuration())


def _preload_pipeline_runner(runner: PipelineRunner, language: str) -> None:
    """Warm tokenizer and morphosyntax models for a processing language.

    Example:
        >>> from thot.tools.search.app import _load_pipeline_runner, _preload_pipeline_runner
        >>> _preload_pipeline_runner(_load_pipeline_runner(), "en")  # doctest: +SKIP
    """
    ThotLogger.info(
        f"Preloading pipeline runner for language {language} at startup"
    )
    document = {
        "content": ["warmup"],
        "language-detection": {"language": language},
    }
    try:
        runner.run(
            document,
            skip_converter=True,
            tasks=["morphosyntax"],
        )
    except Exception as error:
        ThotLogger.warning(
            f"Pipeline preload failed for language {language}",
            trace=str(error),
        )


def _load_pipeline_runners() -> dict[str, PipelineRunner]:
    """Load and preload dedicated pipeline runners for each RAG language.

    Example:
        >>> from thot.tools.search.app import _load_pipeline_runners
        >>> runners = _load_pipeline_runners()  # doctest: +SKIP
    """
    runners: dict[str, PipelineRunner] = {}
    for language in _PIPELINE_PRELOAD_LANGUAGES:
        runner = PipelineRunner(_load_pipeline_configuration())
        _preload_pipeline_runner(runner, language)
        runners[language] = runner
    return runners


def _pipeline_runner_for_language(
    state: AppState,
    language: str,
) -> PipelineRunner | None:
    """Return the preloaded pipeline runner for a request language.

    Example:
        >>> from thot.tools.search.app import AppState, _pipeline_runner_for_language
        >>> _pipeline_runner_for_language(AppState(), "en") is None
        True
    """
    if not state.pipeline_runners:
        return None
    return state.pipeline_runners.get(language) or state.pipeline_runners.get(
        "en"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan hook that wires LLM and Vespa clients.

    Example:
        >>> import inspect
        >>> callable(lifespan)
        True
    """
    state = AppState()
    state.prompts = _load_prompts()
    state.llm = UnifiedLLMWrapper()
    state.vespa = VespaClient()
    state.pipeline_runners = await asyncio.to_thread(_load_pipeline_runners)
    app.state.rag = state
    try:
        yield
    finally:
        if state.llm is not None:
            await state.llm.aclose()
        if state.vespa is not None:
            await state.vespa.aclose()


app = FastAPI(
    title="T-KEIR Vespa RAG API",
    version=TKEIR_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "RAG_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health probe that checks Vespa availability.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(health)
        True
    """
    state: AppState = app.state.rag
    if state.vespa is None or not await state.vespa.health():
        raise HTTPException(status_code=503, detail="Vespa is unavailable")
    return {"status": "ok"}


@app.post("/rag/query", response_model=QueryResponse)
async def rag_query(request: QueryRequest) -> QueryResponse:
    """Run hybrid retrieval and optional LLM answer generation.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(rag_query)
        True
    """
    state: AppState = app.state.rag
    if state.llm is None or state.vespa is None:
        raise HTTPException(
            status_code=503, detail="Application is not initialized"
        )

    query_text = request.query.strip()
    request_started = time.perf_counter()

    step_started = time.perf_counter()
    try:
        query_embedding = await state.llm.embed(query_text)
        pipeline_runner = _pipeline_runner_for_language(
            state,
            request.language,
        )
        if pipeline_runner is None:
            search_query_text = query_text
        else:
            search_query_text = await asyncio.to_thread(
                refine_search_query_text,
                pipeline_runner,
                query_text,
                language=request.language,
            )
    except Exception as error:
        LOGGER.exception("Query generation failed")
        raise HTTPException(
            status_code=502, detail=f"Query generation failed: {error}"
        ) from error
    _log_rag_step(
        "query-generation",
        step_started,
        query=repr(query_text),
        search_query=repr(search_query_text),
    )

    step_started = time.perf_counter()
    try:
        search_response = await state.vespa.hybrid_search(
            search_query_text,
            query_embedding,
            query_embedding,
            hits=request.hits,
        )
        parsed_hits = _parse_hits(search_response)
        retrieved_chunks, rdf_payloads = await _enrich_hits(state, parsed_hits)
    except Exception as error:
        LOGGER.exception("Retrieval failed")
        raise HTTPException(
            status_code=502, detail=f"Retrieval failed: {error}"
        ) from error
    _log_rag_step(
        "vespa-querying",
        step_started,
        vespa_hits=len(parsed_hits),
        chunks=len(retrieved_chunks),
    )

    retrieved_chunks = prioritize_chunks_by_query_match(
        retrieved_chunks,
        query_text,
    )

    step_started = time.perf_counter()
    fused_graph = merge_rdf_graphs(rdf_payloads)
    fused_summary = summarize_graph_for_prompt(
        fused_graph,
        query_text,
        max_triples=_DEFAULT_MAX_TRIPLES_FOR_PROMPT,
    )
    hmi_ontology = build_hmi_ontology(
        rdf_payloads,
        [chunk.chunk_id for chunk in retrieved_chunks],
        chunk_texts={
            chunk.chunk_id: chunk.text_raw for chunk in retrieved_chunks
        },
        max_entities=state.rag_config.ontology.max_entities,
        max_keywords=state.rag_config.ontology.max_keywords,
        min_keyword_length=state.rag_config.ontology.min_keyword_length,
    )
    ontology = FusedOntology.model_validate(hmi_ontology)

    prompt_cfg = _language_prompt_cfg(state.prompts, request.language)
    unavailable_answer = _unavailable_answer(prompt_cfg, request.language)
    chunk_excerpts = _format_chunk_excerpts(
        retrieved_chunks,
        empty_message=_no_chunks_message(prompt_cfg),
        max_chars_per_chunk=_DEFAULT_MAX_CHARS_PER_CHUNK,
        max_chunks=_DEFAULT_MAX_CHUNKS_FOR_PROMPT,
    )
    focus_passages = extract_focus_passages(
        [(chunk.chunk_id, chunk.text_raw) for chunk in retrieved_chunks],
        query_text,
        max_passages=_DEFAULT_MAX_FOCUS_PASSAGES,
    )

    if not retrieved_chunks:
        entity_labels, keyword_labels = extract_highlight_labels(ontology)
        query_term_labels = query_highlight_terms(query_text, retrieved_chunks)
        report_markdown = assemble_report_markdown(
            query=query_text,
            language=request.language,
            short_answer=unavailable_answer,
            detailed_report=build_fallback_detailed_report(
                focus_passages=focus_passages,
                chunk_excerpts=chunk_excerpts,
            ),
            chunks=retrieved_chunks,
            ontology=ontology,
            vespa_hits=len(parsed_hits),
        )
        _log_rag_step(
            "answer-building",
            step_started,
            generated=False,
            chunks=len(retrieved_chunks),
        )
        _log_rag_step(
            "rag-query-total", request_started, query=repr(query_text)
        )
        return QueryResponse(
            answer=unavailable_answer,
            report_markdown=report_markdown,
            highlight_entities=entity_labels,
            highlight_keywords=keyword_labels,
            highlight_query_terms=query_term_labels,
            used_chunk_evidence=False,
            answer_unavailable=True,
            chunks=retrieved_chunks,
            ontology=ontology,
            vespa_hits=len(parsed_hits),
        )

    system_prompt, user_prompt = _build_generation_prompts(
        prompt_cfg,
        fused_summary=fused_summary,
        focus_passages=focus_passages,
        chunk_excerpts=chunk_excerpts,
        query_text=query_text,
        unavailable_answer=unavailable_answer,
    )

    try:
        raw_generation = await state.llm.generate(
            user_prompt,
            system=system_prompt or None,
        )
    except Exception as error:
        LOGGER.exception("Generation failed")
        raise HTTPException(
            status_code=502, detail=f"Generation failed: {error}"
        ) from error

    short_answer, detailed_report = parse_structured_generation(
        raw_generation,
        unavailable_answer=unavailable_answer,
    )
    used_chunk_evidence = False
    short_answer, detailed_report, used_chunk_evidence = apply_chunk_evidence_fallback(
        query_text=query_text,
        short_answer=short_answer,
        detailed_report=detailed_report,
        chunks=retrieved_chunks,
        unavailable_answer=unavailable_answer,
    )
    if not detailed_report.strip():
        detailed_report = build_fallback_detailed_report(
            focus_passages=focus_passages,
            chunk_excerpts=chunk_excerpts,
        )

    entity_labels, keyword_labels = extract_highlight_labels(ontology)
    query_term_labels = query_highlight_terms(query_text, retrieved_chunks)
    report_markdown = assemble_report_markdown(
        query=query_text,
        language=request.language,
        short_answer=short_answer,
        detailed_report=detailed_report,
        chunks=retrieved_chunks,
        ontology=ontology,
        vespa_hits=len(parsed_hits),
    )

    _log_rag_step(
        "answer-building",
        step_started,
        generated=True,
        chunks=len(retrieved_chunks),
    )
    _log_rag_step("rag-query-total", request_started, query=repr(query_text))

    return QueryResponse(
        answer=short_answer,
        report_markdown=report_markdown,
        highlight_entities=entity_labels,
        highlight_keywords=keyword_labels,
        highlight_query_terms=query_term_labels,
        used_chunk_evidence=used_chunk_evidence,
        answer_unavailable=is_unavailable_short_answer(
            short_answer,
            unavailable_answer,
        )
        and not used_chunk_evidence,
        chunks=retrieved_chunks,
        ontology=ontology,
        vespa_hits=len(parsed_hits),
    )


def main() -> None:
    """CLI entry point for the RAG FastAPI server.

    Example:
        >>> from thot.tools.search import app as rag_app
        >>> callable(rag_app.main)
        True
    """
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        "thot.tools.search.app:app",
        host=os.getenv("RAG_HOST", "0.0.0.0"),
        port=int(os.getenv("RAG_PORT", "8090")),
        reload=False,
    )


if __name__ == "__main__":
    main()
