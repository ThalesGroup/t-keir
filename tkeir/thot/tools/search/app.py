"""Title: RAG FastAPI application

FastAPI RAG application over Vespa 2-level document/chunk retrieval.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import yaml
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from rdflib import Graph

from thot import __version__ as TKEIR_VERSION
from thot.action.correlation import current_correlation_id
from thot.action.middleware import ActionCorrelationMiddleware
from thot.action.models import new_action_id
from thot.action.readiness import readiness_report
from thot.core.LlmWrapper import UnifiedLLMWrapper
from thot.core.StructuredLogging import configure_json_logging
from thot.core.ThotLogger import ThotLogger
from thot.core.ThotMetrics import ThotMetrics
from thot.core.TkeirPaths import configs_dir, rag_prompts_path, repo_root
from thot.governor.wiring import wire_governor_middleware
from thot.tasks.pipeline.PipelineConfiguration import PipelineConfiguration
from thot.tasks.pipeline.PipelineRunner import PipelineRunner
from thot.tools.search.business_ontology import (
    business_ontology_to_json_ld,
    resolve_search_business_ontology,
)
from thot.tools.search.generation_prompt import (
    build_focus_query_text,
    format_generation_guidance,
    format_query_analysis_for_prompt,
    is_entity_report_query,
)
from thot.tools.search.ontology_reasoner import (
    DEFAULT_REASONER,
    SUPPORTED_OPERATIONS,
    query_merged_ontology,
)
from thot.tools.search.ontology_utils import (
    build_hmi_ontology,
    enrich_hmi_ontology_from_analyzed_documents,
    extract_focus_passages,
    filter_query_relevant_chunks,
    format_svo_ontology_context,
    merge_rdf_graphs,
    prioritize_chunks_by_query_match,
    summarize_graph_for_prompt,
    truncate_for_prompt,
)
from thot.tools.search.query_analyzer import (
    QueryAnalyzerTask,
    build_svo_match_query,
    format_vespa_query_json,
)
from thot.tools.search.query_refiner import refine_search_query_text
from thot.tools.search.rag_config import (
    RagConfig,
    RagPromptConfig,
    load_rag_config,
    resolve_passage_settings,
)
from thot.tools.search.rag_report import (
    apply_chunk_evidence_fallback,
    assemble_report_markdown,
    build_fallback_detailed_report,
    extract_highlight_labels,
    format_input_prompt,
    is_unavailable_short_answer,
    parse_structured_generation,
    query_highlight_terms,
)
from thot.tools.search.rerank import rerank_vespa_children
from thot.tools.search.search_aggregate import aggregate_chunks_to_documents
from thot.tools.search.user_space import resolve_vespa_user_space
from thot.tools.search.vespa_client import (
    VespaClient,
    clean_chunk_text_for_prompt,
)

LOGGER = logging.getLogger(__name__)
PROMPTS_PATH = rag_prompts_path()

_DEFAULT_UNAVAILABLE_ANSWERS = {
    "en": "The information is not available.",
    "fr": "L'information n'est pas disponible.",
}


class QueryRequest(BaseModel):
    """Full RAG query request with optional generation overrides.

    Example:
        >>> QueryRequest(query="hello").query
        'hello'
    """

    query: str = Field(..., min_length=1)
    language: str = Field(default="en", pattern="^(en|fr)$")
    hits: int = Field(default=20, ge=1, le=100)
    business_ontology: list[dict[str, Any]] | dict[str, Any] | None = Field(
        default=None,
        description=(
            "Per-request business ontology concepts merged with "
            "datasets/<business_ontology_dataset>/business_ontology.yaml"
        ),
    )
    business_ontology_dataset: str | None = Field(
        default=None,
        description=(
            "Dataset folder under datasets/ whose business_ontology.yaml is "
            "auto-loaded (default: rag.yaml dual_hybrid.business_ontology.default_dataset)"
        ),
    )
    analyzed_documents_path: str | None = Field(
        default=None,
        description=(
            "Filesystem path to the ingest dump root (directory with staging/ "
            "and source_refs.json) used to load analyzed_document.json RDF"
        ),
    )
    ontology_json_ld: str | None = Field(
        default=None,
        description=(
            "Optional extra JSON-LD ontology merged into the fused response graph"
        ),
    )
    max_passages: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Override prompt.passages.count from rag.yaml",
    )
    max_chars_per_passage: int | None = Field(
        default=None,
        ge=200,
        le=8000,
        description="Override prompt.passages.max_chars from rag.yaml",
    )
    focus_context_sentences: int | None = Field(
        default=None,
        ge=0,
        le=10,
        description="Override prompt.passages.context_sentences from rag.yaml",
    )
    search_mode: str | None = Field(
        default=None,
        description=(
            "Dual-hybrid retrieval mode: auto | global | user | both. "
            "When set, overrides rag.yaml dual_hybrid.search_mode."
        ),
    )
    source_refs: list[str] | None = Field(
        default=None,
        description=(
            "Restrict retrieval to these Vespa/workspace source_ref values "
            "(typically user:<space>:<path>). Forces search_mode=user."
        ),
    )


class RetrievedChunk(BaseModel):
    """Chunk hit enriched with parent metadata for RAG prompts.

    Example:
        >>> RetrievedChunk(chunk_id="c1", text_raw="hello", parent_doc_id="doc")
        RetrievedChunk(chunk_id='c1', text_raw='hello', parent_doc_id='doc', relevance=None, title='')
    """

    chunk_id: str
    text_raw: str
    parent_doc_id: str
    relevance: float | None = None
    title: str = ""


class SearchRequest(BaseModel):
    """Retrieval-only request (no LLM answer generation).

    Example:
        >>> SearchRequest(query="hello").hits
        20
    """

    query: str = Field(..., min_length=1)
    language: str = Field(default="en", pattern="^(en|fr)$")
    hits: int = Field(default=20, ge=1, le=100)
    business_ontology: list[dict[str, Any]] | dict[str, Any] | None = Field(
        default=None,
        description=(
            "Per-request business ontology concepts merged with "
            "datasets/<business_ontology_dataset>/business_ontology.yaml"
        ),
    )
    business_ontology_dataset: str | None = Field(
        default=None,
        description=(
            "Dataset folder under datasets/ whose business_ontology.yaml is "
            "auto-loaded (default: rag.yaml dual_hybrid.business_ontology.default_dataset)"
        ),
    )
    analyzed_documents_path: str | None = Field(
        default=None,
        description=(
            "Filesystem path to the ingest dump root (directory with staging/ "
            "and source_refs.json) used to load analyzed_document.json RDF"
        ),
    )
    ontology_json_ld: str | None = Field(
        default=None,
        description=(
            "Optional extra JSON-LD ontology merged into the fused response graph"
        ),
    )
    search_mode: str | None = Field(
        default=None,
        description=(
            "Dual-hybrid retrieval mode: auto | global | user | both. "
            "When set, overrides rag.yaml dual_hybrid.search_mode."
        ),
    )
    source_refs: list[str] | None = Field(
        default=None,
        description=(
            "Restrict retrieval to these Vespa/workspace source_ref values "
            "(typically user:<space>:<path>). Forces search_mode=user."
        ),
    )


class SearchChunk(BaseModel):
    """Reranked chunk hit with score.

    Example:
        >>> SearchChunk(
        ...     chunk_id="c1", text_raw="t", parent_doc_id="d1", score=0.9
        ... ).score
        0.9
    """

    chunk_id: str
    text_raw: str
    parent_doc_id: str
    score: float
    title: str = ""


class SearchDocument(BaseModel):
    """Document aggregated from reranked chunk hits.

    Example:
        >>> SearchDocument(document_id="d1", score=0.9).document_id
        'd1'
    """

    document_id: str
    score: float
    chunk_ids: list[str] = Field(default_factory=list)
    title: str = ""
    hit_count: int = 0


class SemanticEntity(BaseModel):
    """Named entity surfaced from fused ontology graphs.

    Example:
        >>> SemanticEntity(label="Paris", type="GPE").label
        'Paris'
    """

    label: str
    type: str
    chunk_ids: list[str] = Field(default_factory=list)
    # Text-importance weight (chunk coverage + summed text hits).
    weight: float = 0.0
    mention_count: int = 0
    text_hits: int = 0


class SemanticKeyword(BaseModel):
    """Keyword surfaced from fused ontology graphs.

    Example:
        >>> SemanticKeyword(label="economy").label
        'economy'
    """

    label: str
    chunk_ids: list[str] = Field(default_factory=list)
    # Text-importance weight (chunk coverage + summed text hits).
    weight: float = 0.0
    mention_count: int = 0
    text_hits: int = 0


class OntologyRelation(BaseModel):
    """Weighted relation summed across fused chunk/parent ontologies.

    Example:
        >>> OntologyRelation(source="a", predicate="p", target="b").predicate
        'p'
    """

    source: str
    predicate: str
    target: str
    weight: float = 1.0


class ProposedOntologyQuery(BaseModel):
    """Suggested SPARQL / expression / coherence query for the Navigator.

    Example:
        >>> ProposedOntologyQuery(
        ...     kind="sparql", title="T", query="SELECT ?s WHERE { ?s ?p ?o }"
        ... ).kind
        'sparql'
    """

    kind: str
    title: str
    query: str
    description: str = ""


class FusedOntology(BaseModel):
    """Merged ontology from Vespa parent ``json_ld`` fields for HMI / reasoner.

    Example:
        >>> FusedOntology(entities=[], keywords=[]).triple_count
        0
    """

    entities: list[SemanticEntity]
    keywords: list[SemanticKeyword]
    json_ld: str = ""
    # Weighted SVO / ontology links (fuse-summed across source payloads).
    relations: list[OntologyRelation] = Field(default_factory=list)
    triple_count: int = 0
    source_count: int = 0
    document_ids: list[str] = Field(default_factory=list)
    proposed_queries: list[ProposedOntologyQuery] = Field(default_factory=list)


class SearchTimings(BaseModel):
    """Per-query retrieval stage timings in milliseconds.

    Example:
        >>> SearchTimings(nlp_ms=1.0, total_ms=2.0).nlp_ms
        1.0
    """

    nlp_ms: float = 0.0
    vespa_ms: float = 0.0
    vespa_chunk_ms: float = 0.0
    vespa_document_ms: float = 0.0
    rrf_ms: float = 0.0
    rerank_ms: float = 0.0
    ontology_ms: float = 0.0
    lexical_ms: float = 0.0
    total_ms: float = 0.0


class SearchResponse(BaseModel):
    """Reranked chunks and documents for a search query.

    Example:
        >>> SearchResponse(
        ...     query="q", chunks=[], documents=[], vespa_hits=0
        ... ).query
        'q'
    """

    query: str
    chunks: list[SearchChunk]
    documents: list[SearchDocument]
    vespa_hits: int
    ranking_profile: str | None = None
    # Global = merged parent/chunk document ontologies (degree hubs on left).
    ontology: FusedOntology | None = None
    # Query NLP (+ matched external BO) document ontology.
    query_ontology: FusedOntology | None = None
    # Union of query_ontology + chunk-fused ontology.
    merged_ontology: FusedOntology | None = None
    timings: SearchTimings | None = None


class QueryResponse(BaseModel):
    """RAG answer with report markdown, highlights, and retrieved chunks.

    Example:
        >>> QueryResponse(
        ...     answer="N/A",
        ...     report_markdown="",
        ...     chunks=[],
        ...     ontology=FusedOntology(entities=[], keywords=[]),
        ...     vespa_hits=0,
        ... ).answer
        'N/A'
    """

    answer: str
    report_markdown: str
    input_prompt: str = ""
    vespa_query: str = ""
    highlight_entities: list[str] = Field(default_factory=list)
    highlight_keywords: list[str] = Field(default_factory=list)
    highlight_query_terms: list[str] = Field(default_factory=list)
    used_chunk_evidence: bool = False
    answer_unavailable: bool = False
    chunks: list[RetrievedChunk]
    ontology: FusedOntology
    vespa_hits: int


class OntologyReasonerRequest(BaseModel):
    """Follow-up ontology query over a fused RAG / search ontology.

    Example:
        >>> OntologyReasonerRequest(json_ld="[]").operation
        'sparql'
    """

    json_ld: str = Field(
        ...,
        min_length=1,
        description="Fused ontology JSON-LD from a prior /search or /rag/query",
    )
    operation: str = Field(
        default="sparql",
        description=f"One of {', '.join(SUPPORTED_OPERATIONS)}",
    )
    class_iri: str | None = Field(
        default=None,
        description="Class IRI for subclasses / superclasses / instances",
    )
    individual_iri: str | None = Field(
        default=None,
        description="Individual IRI for types",
    )
    sparql: str | None = Field(
        default=None,
        description="SPARQL SELECT for operation=sparql",
    )
    expression: str | None = Field(
        default=None,
        description=(
            "Manchester-like expression for operation=expression "
            "(e.g. 'Person and age > 20')"
        ),
    )
    reasoner: str = Field(
        default=DEFAULT_REASONER,
        description=f"Reasoner engine (only {DEFAULT_REASONER!r})",
    )
    direct: bool = False
    limit: int = Field(default=50, ge=1, le=500)
    business_ontology: list[dict[str, Any]] | dict[str, Any] | None = Field(
        default=None,
        description="Optional business ontology payload merged before reasoning",
    )
    business_ontology_dataset: str | None = Field(
        default=None,
        description=(
            "Dataset folder under datasets/ whose business_ontology.yaml is "
            "merged into the reasoner graph"
        ),
    )


class OntologyReasonerResponse(BaseModel):
    """Result of an ontology reasoner follow-up query.

    Example:
        >>> OntologyReasonerResponse(operation="sparql", backend="none").count
        0
    """

    operation: str
    backend: str
    reasoner: str = DEFAULT_REASONER
    results: list[dict[str, str]] = Field(default_factory=list)
    count: int = 0
    consistent: bool | None = None
    triple_count: int = 0
    note: str | None = None
    json_ld: str | None = None
    expression: str | None = None
    sparql: str | None = None


class AppState:
    """Mutable RAG service state shared across HTTP handlers.

    Example:
        >>> from thot.tools.search.app import AppState
        >>> isinstance(AppState().rag_config, RagConfig)
        True
    """

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
        self.dual_pipeline: Any | None = None


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
_PIPELINE_PRELOAD_LANGUAGES = ("en", "fr")


def _timings_from_dual_ms(
    raw: dict[str, float] | None,
    *,
    embed_ms: float = 0.0,
    total_ms: float | None = None,
) -> SearchTimings:
    """Map dual-hybrid ``timings_ms`` (+ optional embed) to SearchTimings.

    Example:
        >>> t = _timings_from_dual_ms({"nlp": 1.0, "vespa_chunk": 2.0})
        >>> t.nlp_ms
        1.0
        >>> t.vespa_ms
        2.0
    """
    data = dict(raw or {})
    nlp = float(data.get("nlp") or data.get("expand") or 0.0) + float(embed_ms)
    vespa_chunk = float(data.get("vespa_chunk") or 0.0)
    vespa_document = float(data.get("vespa_document") or 0.0)
    if not vespa_chunk and not vespa_document and data.get("vespa_arms"):
        # Legacy single bucket.
        vespa_chunk = float(data["vespa_arms"])
    rrf = float(data.get("rrf") or 0.0)
    rerank = float(data.get("rerank") or data.get("cross_encoder") or 0.0)
    ontology = float(data.get("ontology") or 0.0)
    lexical = float(data.get("lexical") or 0.0)
    computed_total = (
        nlp + vespa_chunk + vespa_document + rrf + rerank + ontology + lexical
    )
    vespa = vespa_chunk + vespa_document
    return SearchTimings(
        nlp_ms=round(nlp, 3),
        vespa_ms=round(vespa, 3),
        vespa_chunk_ms=round(vespa_chunk, 3),
        vespa_document_ms=round(vespa_document, 3),
        rrf_ms=round(rrf, 3),
        rerank_ms=round(rerank, 3),
        ontology_ms=round(ontology, 3),
        lexical_ms=round(lexical, 3),
        total_ms=round(
            float(total_ms) if total_ms is not None else computed_total, 3
        ),
    )


def _log_search_timings(
    timings: SearchTimings,
    *,
    query: str,
    ranking_profile: str | None,
) -> None:
    """Log per-query stage timings with correlation id.

    Example:
        >>> from thot.tools.search.app import SearchTimings, _log_search_timings
        >>> _log_search_timings(
        ...     SearchTimings(nlp_ms=1.0, total_ms=2.0),
        ...     query="hello",
        ...     ranking_profile="hybrid",
        ... )  # doctest: +SKIP
    """
    cid = current_correlation_id() or ""
    qpreview = " ".join(str(query).split())
    if len(qpreview) > 80:
        qpreview = qpreview[:79] + "…"
    ThotLogger.info(
        "Search timings "
        f"correlation_id={cid} "
        f"nlp_ms={timings.nlp_ms:.1f} "
        f"vespa_ms={timings.vespa_ms:.1f} "
        f"(chunk={timings.vespa_chunk_ms:.1f} "
        f"document={timings.vespa_document_ms:.1f}) "
        f"rrf_ms={timings.rrf_ms:.1f} "
        f"rerank_ms={timings.rerank_ms:.1f} "
        f"total_ms={timings.total_ms:.1f} "
        f"ranking_profile={ranking_profile or '-'} "
        f"query={qpreview!r}"
    )


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
    query_analysis: str,
    generation_guidance: str,
    unavailable_answer: str,
    user_prompt_template: str | None = None,
    system_prompt_template: str | None = None,
) -> tuple[str, str]:
    """Build system and user prompts for answer generation.

    Example:
        >>> cfg = {"user": "Q:{query_text} G:{generation_guidance}", "system": "S:{unavailable_answer}"}
        >>> _build_generation_prompts(cfg, fused_summary="", focus_passages="p", chunk_excerpts="", query_text="Hi", query_analysis="- terms: hi", generation_guidance="Mode: general", unavailable_answer="N/A")
        ('S:N/A', 'Q:Hi G:Mode: general')
    """
    format_kwargs = {
        "fused_graph_triples_or_summary": fused_summary,
        "focus_passages": focus_passages,
        "chunk_excerpts": chunk_excerpts,
        "query_text": query_text,
        "query_analysis": query_analysis,
        "generation_guidance": generation_guidance,
        "unavailable_answer": unavailable_answer,
    }
    user_template = user_prompt_template or prompt_cfg["user"]
    user_prompt = user_template.format(**format_kwargs)
    system_template = system_prompt_template or prompt_cfg.get("system", "")
    system_prompt = system_template.format(**format_kwargs)
    return system_prompt.strip(), user_prompt.strip()


def _resolve_user_prompt_template(
    prompt_cfg: dict[str, Any],
    prompt_settings: RagPromptConfig,
) -> str:
    """Pick the user prompt template for the configured chunk context mode.

    Example:
        >>> cfg = {"user": "default", "user_svo": "svo"}
        >>> _resolve_user_prompt_template(cfg, RagPromptConfig("svo_ontology", 80))
        'svo'
    """
    if prompt_settings.chunk_context_mode == "svo_ontology":
        return str(prompt_cfg.get("user_svo") or prompt_cfg["user"])
    return str(prompt_cfg["user"])


def _resolve_system_prompt_template(
    prompt_cfg: dict[str, Any],
    prompt_settings: RagPromptConfig,
) -> str | None:
    """Pick the system prompt template for the configured chunk context mode.

    Example:
        >>> cfg = {"system": "default", "system_svo": "svo"}
        >>> _resolve_system_prompt_template(cfg, RagPromptConfig("svo_ontology", 80))
        'svo'
    """
    if prompt_settings.chunk_context_mode == "svo_ontology":
        configured = prompt_cfg.get("system_svo")
        return str(configured) if configured else None
    return None


def _uses_svo_only_prompt(prompt_settings: RagPromptConfig) -> bool:
    """Return whether generation should use the compact SVO-only prompt.

    Example:
        >>> from thot.tools.search.app import _uses_svo_only_prompt
        >>> from thot.tools.search.rag_config import RagPromptConfig
        >>> _uses_svo_only_prompt(
        ...     RagPromptConfig(chunk_context_mode="svo_ontology", max_svo_triples=12)
        ... )
        True
    """
    return prompt_settings.chunk_context_mode == "svo_ontology"


def _format_chunk_context(
    *,
    prompt_settings: RagPromptConfig,
    graph: Graph,
    query_text: str,
    chunks: list[RetrievedChunk],
    empty_message: str,
    max_chars_per_chunk: int,
    max_chunks: int,
) -> str:
    """Build chunk-context text for the LLM user prompt.

    Example:
        >>> from thot.tools.search.app import _format_chunk_context
        >>> from thot.tools.search.rag_config import RagPromptConfig
        >>> from rdflib import Graph
        >>> _format_chunk_context(
        ...     prompt_settings=RagPromptConfig(
        ...         chunk_context_mode="svo_ontology",
        ...         max_svo_triples=12,
        ...     ),
        ...     graph=Graph(),
        ...     query_text="test",
        ...     chunks=[],
        ...     empty_message="No context.",
        ...     max_chars_per_chunk=100,
        ...     max_chunks=3,
        ... )
        'No context.'
    """
    if prompt_settings.chunk_context_mode == "svo_ontology":
        return format_svo_ontology_context(
            graph,
            query_text,
            chunks,
            empty_message=empty_message,
            max_triples=prompt_settings.max_svo_triples,
        )
    return _format_chunk_excerpts(
        chunks,
        empty_message=empty_message,
        max_chars_per_chunk=max_chars_per_chunk,
        max_chunks=max_chunks,
    )


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
            clean_chunk_text_for_prompt(chunk.text_raw),
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
    ontology = parent_fields.get("document_ontology")
    if isinstance(ontology, dict):
        for key in ("json_ld", "rdf_graph_serialized"):
            value = ontology.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return ""


def _resolve_analyzed_documents_root(
    analyzed_documents_path: str | None = None,
) -> Path:
    """Resolve ingest dump root for analyzed_document.json lookups.

    Preference order:
    1. Explicit ``analyzed_documents_path`` request parameter
    2. ``INGEST_ROOT`` (``ingest_settings().root``)
    3. ``<repo>/workspace/ingest``

    Example:
        >>> from pathlib import Path
        >>> isinstance(_resolve_analyzed_documents_root(), Path)
        True
    """
    candidates: list[Path] = []
    if analyzed_documents_path and str(analyzed_documents_path).strip():
        raw = Path(str(analyzed_documents_path).strip()).expanduser()
        candidates.append(
            raw if raw.is_absolute() else Path(repo_root()) / raw
        )
    try:
        from thot.tools.ingest.config import ingest_settings

        candidates.append(Path(ingest_settings().root))
    except Exception:  # noqa: BLE001
        pass
    candidates.append(Path(repo_root()) / "workspace" / "ingest")

    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_dir():
            return path
    return candidates[0]


def _ingest_store_parent(
    source_ref: str,
    *,
    analyzed_documents_path: str | None = None,
) -> dict[str, Any]:
    """Fallback analyzed document lookup from ingest staging by ``source_ref``.

    Example:
        >>> _ingest_store_parent("")
        {}
    """
    if not source_ref.strip():
        return {}
    try:
        from thot.tools.ingest.store import IngestStore

        store = IngestStore(
            _resolve_analyzed_documents_root(analyzed_documents_path)
        )
        doc = store.read_analyzed_document_by_source_ref(source_ref)
        if not isinstance(doc, dict):
            return {}
        return doc
    except Exception:
        LOGGER.warning(
            "Unable to load analyzed ingest document for %s", source_ref
        )
        return {}


def _collect_source_ref_rdf_payloads(
    source_refs: list[str] | None,
    *,
    analyzed_documents_path: str | None = None,
) -> list[str]:
    """Load JSON-LD from analyzed documents for every basket ``source_ref``.

    Used so My-files brief / ontology fusion does not depend solely on which
    passages Vespa returned — indexed docs still contribute their NLP graphs.

    Example:
        >>> _collect_source_ref_rdf_payloads(None)
        []
    """
    payloads: list[str] = []
    seen: set[str] = set()
    for ref in _normalize_source_refs(source_refs):
        doc = _ingest_store_parent(
            ref,
            analyzed_documents_path=analyzed_documents_path,
        )
        rdf = _extract_parent_rdf(doc)
        if not rdf or rdf in seen:
            continue
        seen.add(rdf)
        payloads.append(rdf)
    return payloads


def _merge_rdf_payload_lists(*lists: list[str]) -> list[str]:
    """Concatenate RDF JSON-LD strings with de-duplication.

    Example:
        >>> _merge_rdf_payload_lists(["<a>"], ["<a>", "<b>"])
        ['<a>', '<b>']
    """
    out: list[str] = []
    seen: set[str] = set()
    for group in lists:
        for item in group:
            text = (item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)
    return out


def _resolve_request_business_ontology(
    state: AppState,
    *,
    business_ontology: Any = None,
    business_ontology_dataset: str | None = None,
) -> dict[str, Any] | None:
    """Load default dataset YAML and merge with the request payload.

    Example:
        >>> from thot.tools.search.app import AppState, _resolve_request_business_ontology
        >>> isinstance(_resolve_request_business_ontology(AppState()), dict)
        True
    """
    bo_cfg = state.rag_config.dual_hybrid.business_ontology
    dataset = (
        (business_ontology_dataset or "").strip()
        or (bo_cfg.default_dataset or "osint").strip()
        or "osint"
    )
    return resolve_search_business_ontology(
        dataset=dataset,
        request_payload=business_ontology,
        search_enabled=bo_cfg.search_enabled,
    )


def _empty_fused_ontology() -> FusedOntology:
    """Return an empty HMI ontology payload.

    Example:
        >>> _empty_fused_ontology().entities
        []
    """
    return FusedOntology(entities=[], keywords=[], json_ld="[]")


def _build_query_ontology(
    state: AppState,
    *,
    query_text: str,
    language: str | None,
    query_analysis: dict[str, Any] | None,
    business_ontology_payload: dict[str, Any] | None = None,
) -> FusedOntology:
    """Run document_ontology on the query NLP doc (+ matched external BO).

    Prefers ``query_analysis['_pipeline_doc']`` from
    :class:`PassageRetrievalPipeline` so we do not re-run NLP.

    Example:
        >>> from thot.tools.search.app import AppState, _build_query_ontology
        >>> o = _build_query_ontology(
        ...     AppState(), query_text="hello", language="en", query_analysis={}
        ... )
        >>> o.entities
        []
    """
    from thot.tasks.answer_generation.ontology_clues import (
        build_document_ontology_json_ld,
    )
    from thot.tools.search.business_ontology import (
        annotate_document_with_business_ontology,
    )
    from thot.tools.search.query_analyzer import run_linguistic_pipeline

    analysis = query_analysis if isinstance(query_analysis, dict) else {}
    document: dict[str, Any] | None = None
    pipeline_doc = analysis.get("_pipeline_doc")
    if isinstance(pipeline_doc, dict) and pipeline_doc:
        document = dict(pipeline_doc)
    else:
        lang = (language or "en").strip() or "en"
        runner = _pipeline_runner_for_language(state, lang)
        if runner is not None and (query_text or "").strip():
            try:
                document = run_linguistic_pipeline(
                    runner, query_text, language=lang
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Query ontology NLP failed: %s", exc)
                document = None
    if not document:
        # Minimal fallback from analysis surfaces (no full pipeline doc).
        document = {
            "content": [query_text],
            "content_ner": [
                {
                    "text": str(row.get("text") or ""),
                    "label": str(row.get("label") or "entity"),
                }
                for row in analysis.get("ner_entities") or []
                if isinstance(row, dict) and str(row.get("text") or "").strip()
            ],
            "keywords": list(analysis.get("keywords") or []),
        }
        if language:
            document["language-detection"] = {"language": language}

    document.setdefault("source_doc_id", "query://search")
    document.setdefault("source", "query://search")
    if language and "language-detection" not in document:
        document["language-detection"] = {"language": language}

    try:
        json_ld = build_document_ontology_json_ld(document)
        document["document_ontology"] = {"json_ld": json_ld}
        if business_ontology_payload:
            document = annotate_document_with_business_ontology(
                document, business_ontology_payload
            )
        ontology_block = document.get("document_ontology") or {}
        final_ld = str(ontology_block.get("json_ld") or json_ld or "[]")
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Query ontology build failed: %s", exc)
        return _empty_fused_ontology()

    if not final_ld.strip() or final_ld.strip() == "[]":
        return _empty_fused_ontology()

    hmi = build_hmi_ontology(
        [final_ld],
        [],
        document_ids=["query://search"],
        max_entities=state.rag_config.ontology.max_entities,
        max_keywords=state.rag_config.ontology.max_keywords,
        min_keyword_length=state.rag_config.ontology.min_keyword_length,
    )
    # Query graphs often lack DocumentChunk anchors — backfill surfaces from NLP.
    if not hmi.get("entities"):
        entities = []
        for row in analysis.get("ner_entities") or []:
            if not isinstance(row, dict):
                continue
            label = str(row.get("text") or "").strip()
            if not label:
                continue
            entities.append(
                {
                    "label": label,
                    "type": str(row.get("label") or "entity"),
                    "chunk_ids": ["query://search"],
                }
            )
        hmi["entities"] = entities[: state.rag_config.ontology.max_entities]
    if not hmi.get("keywords"):
        keywords = []
        for raw in analysis.get("keywords") or []:
            if isinstance(raw, dict):
                label = str(raw.get("text") or raw.get("label") or "").strip()
            else:
                label = str(raw or "").strip()
            if len(label) >= state.rag_config.ontology.min_keyword_length:
                keywords.append(
                    {"label": label, "chunk_ids": ["query://search"]}
                )
        hmi["keywords"] = keywords[: state.rag_config.ontology.max_keywords]
    return FusedOntology.model_validate(hmi)


def _fuse_response_ontology(
    state: AppState,
    *,
    rdf_payloads: list[str],
    retrieved_chunks: list[RetrievedChunk],
    business_ontology_payload: dict[str, Any] | None = None,
    ontology_json_ld: str | None = None,
    document_ids: list[str] | None = None,
    include_full_business_ontology: bool = False,
    analyzed_documents_path: str | None = None,
) -> FusedOntology:
    """Merge document RDF (+ optional request JSON-LD) for HMI display.

    By default the full business-ontology catalog is **not** dumped into the
    fused graph — that swamps degree ranking with taxonomy hubs. Matched BO
    concepts already live on parent/query ``document_ontology`` via annotate.
    Set ``include_full_business_ontology=True`` for reasoner-only callers that
    still need the catalog.

    ``document_ids`` (e.g. basket ``source_refs``) anchors entity export when
    Vespa returned no chunks but analyzed dumps were fused by source_ref.

    After RDF export, ``kg`` / ``content_ner`` / ``keywords`` are re-read from
    each parent ``analyzed_document.json`` (index-time dump) and merged in so
    NLP signals stay visible without changing ingest.

    Example:
        >>> from thot.tools.search.app import AppState, _fuse_response_ontology
        >>> o = _fuse_response_ontology(AppState(), rdf_payloads=[], retrieved_chunks=[])
        >>> o.entities
        []
    """
    fused_docs = list(rdf_payloads)
    if include_full_business_ontology and business_ontology_payload:
        business_json_ld = business_ontology_to_json_ld(
            business_ontology_payload
        )
        if business_json_ld and business_json_ld != "[]":
            fused_docs.append(business_json_ld)
    extra = (ontology_json_ld or "").strip()
    if extra:
        fused_docs.append(extra)
    parent_ids = [
        chunk.parent_doc_id
        for chunk in retrieved_chunks
        if chunk.parent_doc_id
    ]
    if document_ids:
        parent_ids = list(document_ids) + parent_ids
    hmi_ontology = build_hmi_ontology(
        fused_docs,
        [chunk.chunk_id for chunk in retrieved_chunks],
        chunk_texts={
            chunk.chunk_id: chunk.text_raw for chunk in retrieved_chunks
        },
        document_ids=parent_ids,
        max_entities=state.rag_config.ontology.max_entities,
        max_keywords=state.rag_config.ontology.max_keywords,
        min_keyword_length=state.rag_config.ontology.min_keyword_length,
    )

    # Search/RAG-time reinforce: load TKEIR analyzed dumps for retrieved chunks.
    analyzed_by_parent: dict[str, dict[str, Any]] = {}
    chunk_parent_ids: dict[str, str] = {}
    for chunk in retrieved_chunks:
        parent = str(chunk.parent_doc_id or "").strip()
        cid = str(chunk.chunk_id or "").strip()
        if not cid:
            continue
        if parent:
            chunk_parent_ids[cid] = parent
            if parent not in analyzed_by_parent:
                doc = _ingest_store_parent(
                    parent,
                    analyzed_documents_path=analyzed_documents_path,
                )
                if doc:
                    analyzed_by_parent[parent] = doc
                    # Also index by source_doc_id / source for lookups.
                    alt = str(doc.get("source_doc_id") or "").strip()
                    if alt and alt not in analyzed_by_parent:
                        analyzed_by_parent[alt] = doc
                    src = str(doc.get("source") or "").strip()
                    if src and src not in analyzed_by_parent:
                        analyzed_by_parent[src] = doc
    if analyzed_by_parent and chunk_parent_ids:
        hmi_ontology = enrich_hmi_ontology_from_analyzed_documents(
            hmi_ontology,
            analyzed_documents=analyzed_by_parent,
            chunk_parent_ids=chunk_parent_ids,
            chunk_texts={
                chunk.chunk_id: chunk.text_raw for chunk in retrieved_chunks
            },
            max_entities=state.rag_config.ontology.max_entities,
            max_keywords=state.rag_config.ontology.max_keywords,
            min_keyword_length=state.rag_config.ontology.min_keyword_length,
        )

    return FusedOntology.model_validate(hmi_ontology)


def _attach_proposed_queries(
    ontology: FusedOntology,
    *,
    query: str,
    query_analysis: dict[str, Any] | None = None,
) -> FusedOntology:
    """Attach SPARQL / expression / coherence proposals for the Navigator.

    Example:
        >>> from thot.tools.search.app import FusedOntology, _attach_proposed_queries
        >>> o = FusedOntology(entities=[], keywords=[])
        >>> _attach_proposed_queries(o, query="hello").proposed_queries[0].kind
        'coherence'
    """
    from thot.tasks.answer_generation.ontology_clues import (
        propose_queries_for_navigator,
    )

    analysis = query_analysis if isinstance(query_analysis, dict) else {}
    entity_types = sorted(
        {entity.type for entity in ontology.entities if entity.type}
    )
    chunk_entities = [
        {
            "label": entity.label,
            "type": entity.type,
            "chunk_ids": list(entity.chunk_ids),
        }
        for entity in ontology.entities
    ]
    chunk_keywords = [
        {
            "label": keyword.label,
            "chunk_ids": list(keyword.chunk_ids),
        }
        for keyword in ontology.keywords
    ]
    try:
        raw = propose_queries_for_navigator(
            analysis,
            query,
            ontology_json_ld=ontology.json_ld,
            entity_types=entity_types,
            chunk_entities=chunk_entities,
            chunk_keywords=chunk_keywords,
        )
    except Exception:  # noqa: BLE001
        LOGGER.exception("Failed to build ontology navigator proposals")
        return ontology
    proposals = [
        ProposedOntologyQuery.model_validate(item)
        for item in raw
        if isinstance(item, dict)
    ]
    return ontology.model_copy(update={"proposed_queries": proposals})


async def _enrich_hits(
    state: AppState,
    parsed_hits: list[tuple[dict[str, Any], float | None]],
    *,
    analyzed_documents_path: str | None = None,
) -> tuple[list[RetrievedChunk], list[str]]:
    """Attach parent document metadata to Vespa chunk hits.

    Parent fetches run concurrently (bounded by
    ``vespa.concurrency.enrich_workers``).

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(_enrich_hits)
        True
    """
    parent_cache: dict[str, dict[str, Any]] = {}
    doc_refs = {
        str(
            fields.get("doc_ref")
            or fields.get("source_doc_id")
            or fields.get("source_ref")
            or ""
        )
        for fields, _ in parsed_hits
        if fields.get("doc_ref")
        or fields.get("source_doc_id")
        or fields.get("source_ref")
    }
    workers = max(1, state.rag_config.vespa.concurrency.enrich_workers)
    semaphore = asyncio.Semaphore(workers)

    def _load_ingest(doc_ref: str) -> dict[str, Any]:
        """Load analyzed parent fields from ingest staging for ``doc_ref``.

        Example:
            >>> True
            True
        """
        return _ingest_store_parent(
            doc_ref,
            analyzed_documents_path=analyzed_documents_path,
        )

    async def _fetch_parent(doc_ref: str) -> tuple[str, dict[str, Any]]:
        """Fetch parent document fields from Vespa or ingest fallback.

        Example:
            >>> True
            True
        """
        if state.vespa is None:
            return doc_ref, _load_ingest(doc_ref)
        async with semaphore:
            try:
                # Passage schemas use source_ref, not a Vespa parent doc id —
                # try Vespa only when the id looks like id:…; else load analyzed.
                if doc_ref.startswith("id:"):
                    parent = await state.vespa.get_document_by_ref(doc_ref)
                    if isinstance(parent, dict) and _extract_parent_rdf(
                        parent
                    ):
                        return doc_ref, parent
                    fallback = _load_ingest(doc_ref)
                    return doc_ref, fallback or parent
                return doc_ref, _load_ingest(doc_ref)
            except Exception:
                LOGGER.warning("Unable to fetch parent document %s", doc_ref)
                return doc_ref, _load_ingest(doc_ref)

    if doc_refs:
        fetched = await asyncio.gather(
            *(_fetch_parent(doc_ref) for doc_ref in doc_refs)
        )
        parent_cache.update(fetched)

    retrieved_chunks: list[RetrievedChunk] = []
    rdf_payloads: list[str] = []
    for fields, relevance in parsed_hits:
        chunk_id = str(fields.get("chunk_id") or "")
        text_raw = str(
            fields.get("text_raw") or fields.get("chunk_text") or ""
        )
        if not chunk_id or not text_raw:
            continue

        parent_key = str(
            fields.get("doc_ref")
            or fields.get("source_doc_id")
            or fields.get("source_ref")
            or ""
        )
        parent_fields = parent_cache.get(parent_key, {}) if parent_key else {}
        parent_doc_id = str(
            fields.get("source_doc_id")
            or fields.get("source_ref")
            or parent_fields.get("source_doc_id")
            or parent_key
            or ""
        )
        title = str(
            fields.get("title") or parent_fields.get("title") or ""
        ).strip()
        # Prefer json_ld already on the hit (dual hybrid) over a parent fetch.
        rdf_source = fields if fields.get("json_ld") else parent_fields
        retrieved_chunks.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                text_raw=text_raw,
                parent_doc_id=parent_doc_id,
                relevance=relevance,
                title=title,
            )
        )
        rdf_payloads.append(_extract_parent_rdf(rdf_source))

    return retrieved_chunks, rdf_payloads


async def _retrieve_and_rerank(
    state: AppState,
    *,
    query_text: str,
    language: str,
    hits: int,
    user_space: str | None = None,
    business_ontology: Any | None = None,
    search_mode: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None, str]:
    """Run query analysis, Vespa search, and optional second-stage rerank.

    When ``dual_hybrid.enabled`` is true, runs :class:`PassageRetrievalPipeline`
    (global / user / both modes with BGE-M3 dense+sparse).

    Returns:
        ``(search_response, vespa_payload, query_analysis, search_query_text)``.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(_retrieve_and_rerank)
        True
    """
    assert state.vespa is not None
    space = user_space or state.vespa.config.user_space
    query_analysis: dict[str, Any] | None = None
    dual_cfg = state.rag_config.dual_hybrid
    if dual_cfg.enabled:
        from thot.tools.search.passage_retrieval import (
            PassageRetrievalPipeline,
            SearchMode,
        )

        pipeline_mode: SearchMode | None = None
        if search_mode in ("global", "user", "both", "auto"):
            pipeline_mode = cast(SearchMode, search_mode)

        pipeline = PassageRetrievalPipeline(
            dual_cfg,
            state.vespa,
            pipeline_runner=_pipeline_runner_for_language(state, language),
        )
        result = await pipeline.search(
            query_text,
            user_space=space,
            language=language,
            business_ontology=business_ontology,
            mode=pipeline_mode,
            top_k=hits,
        )
        # Shape as Vespa-like response for downstream enrichers.
        # Must include chunk_id — _enrich_hits skips hits without it.
        children = []
        for hit in result.hits[:hits]:
            children.append(
                {
                    "id": hit.passage_id,
                    "relevance": hit.score,
                    "fields": {
                        "chunk_id": hit.passage_id,
                        "source_ref": hit.source_ref,
                        "source_doc_id": hit.source_ref,
                        "doc_ref": hit.source_ref,
                        "chunk_text": hit.chunk_text,
                        "text_raw": hit.chunk_text,
                        "ontology_concepts": hit.ontology_concepts,
                        "schema": hit.schema,
                    },
                }
            )
        search_response = {"root": {"children": children}}
        timings_ms = dict(result.timings_ms or {})
        query_analysis = {
            "raw_query": query_text,
            "lexical_query": (
                " ".join(result.expansion_terms[:12]) or query_text
            ),
            "ranking_profile": f"passage/{result.mode}",
            "dual_hybrid": {
                "timings_ms": timings_ms,
                "mode": result.mode,
                "expansion_terms": result.expansion_terms,
            },
            "timings_ms": timings_ms,
        }
        if result.query_analysis:
            query_analysis.update(result.query_analysis)
            query_analysis["dual_hybrid"] = {
                "timings_ms": timings_ms,
                "mode": result.mode,
                "expansion_terms": result.expansion_terms,
            }
        return search_response, None, query_analysis, query_text

    pipeline_runner = _pipeline_runner_for_language(state, language)
    search_query_text = query_text
    vespa_payload: dict[str, Any] | None = None
    rerank_cfg = state.rag_config.search.rerank
    first_stage_hits = hits
    if rerank_cfg.enabled:
        first_stage_hits = max(hits, rerank_cfg.candidates)

    if (
        state.rag_config.search.enabled
        and pipeline_runner is not None
        and state.llm is not None
        and state.vespa is not None
    ):
        analyzer = QueryAnalyzerTask(
            pipeline_runner,
            state.llm,
            state.rag_config.search,
            embedding_dim=state.vespa.config.embedding_dim,
            timeout_seconds=state.vespa.config.timeout_seconds,
            user_space=space,
        )
        analyzed = await analyzer.process(
            query_text,
            language=language,
            hits=first_stage_hits,
        )
        vespa_payload = analyzed["payload"]
        search_response = await state.vespa.search(vespa_payload)
        query_analysis = analyzed["analysis"]
        search_query_text = query_analysis.get("lexical_query") or query_text
    else:
        assert state.llm is not None and state.vespa is not None
        query_embedding = await state.llm.embed(query_text)
        if pipeline_runner is None:
            search_query_text = query_text
        else:
            search_query_text = await asyncio.to_thread(
                refine_search_query_text,
                pipeline_runner,
                query_text,
                language=language,
            )
        vespa_payload = state.vespa.build_hybrid_search_payload(
            search_query_text,
            query_embedding,
            hits=first_stage_hits,
            user_space=space,
        )
        search_response = await state.vespa.search(vespa_payload)
        query_analysis = {
            "raw_query": query_text,
            "lexical_query": search_query_text,
            "search_terms": search_query_text.split(),
        }

    if (
        rerank_cfg.enabled
        and state.llm is not None
        and search_response is not None
    ):
        root = dict(search_response.get("root") or {})
        children = list(root.get("children") or [])
        candidate_n = min(len(children), rerank_cfg.candidates)
        reranked = await rerank_vespa_children(
            state.llm,
            query_text,
            children[:candidate_n],
            top_n=hits,
            strategy=rerank_cfg.strategy,
        )
        root["children"] = reranked
        search_response = {**search_response, "root": root}

    return search_response, vespa_payload, query_analysis, search_query_text


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


def _normalize_source_refs(source_refs: list[str] | None) -> list[str]:
    """Deduplicate non-empty ``source_ref`` values preserving order.

    Example:
        >>> _normalize_source_refs(["a", "a", ""])
        ['a']
    """
    if not source_refs:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in source_refs:
        ref = str(raw or "").strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        out.append(ref)
    return out


def _fields_source_ref(fields: dict[str, Any]) -> str:
    """Best-effort source_ref from a Vespa hit fields dict.

    Example:
        >>> _fields_source_ref({"source_ref": "user:1:doc"})
        'user:1:doc'
    """
    return str(
        fields.get("source_ref")
        or fields.get("source_doc_id")
        or fields.get("doc_ref")
        or fields.get("parent_doc_id")
        or ""
    ).strip()


def _filter_hits_by_source_refs(
    parsed_hits: list[tuple[dict[str, Any], float | None]],
    source_refs: list[str] | None,
) -> list[tuple[dict[str, Any], float | None]]:
    """Keep only hits whose source_ref is in the allowed basket set.

    Example:
        >>> hits = [({"source_ref": "a"}, 1.0), ({"source_ref": "b"}, 0.5)]
        >>> _filter_hits_by_source_refs(hits, ["a"])
        [({'source_ref': 'a'}, 1.0)]
    """
    allowed = set(_normalize_source_refs(source_refs))
    if not allowed:
        return parsed_hits
    filtered: list[tuple[dict[str, Any], float | None]] = []
    for fields, relevance in parsed_hits:
        ref = _fields_source_ref(fields)
        if not ref:
            continue
        if ref in allowed or any(
            ref.startswith(f"{prefix}#") or ref.startswith(f"{prefix}/")
            for prefix in allowed
        ):
            filtered.append((fields, relevance))
    return filtered


def _resolve_search_mode_for_refs(
    search_mode: str | None,
    source_refs: list[str] | None,
) -> str | None:
    """Force user-arm retrieval when restricting to workspace source_refs.

    Example:
        >>> _resolve_search_mode_for_refs("global", ["user:1:x"])
        'user'
        >>> _resolve_search_mode_for_refs("global", None)
        'global'
    """
    if _normalize_source_refs(source_refs):
        return "user"
    return search_mode


def _retrieve_hits_budget(hits: int, source_refs: list[str] | None) -> int:
    """Over-fetch when post-filtering by source_refs so enough evidence remains.

    Example:
        >>> _retrieve_hits_budget(10, None)
        10
        >>> _retrieve_hits_budget(10, ["a"])
        40
    """
    refs = _normalize_source_refs(source_refs)
    if not refs:
        return hits
    return min(100, max(hits, len(refs) * 8, 40))


def _load_pipeline_configuration() -> PipelineConfiguration:
    """Load the bundled pipeline configuration.

    Example:
        >>> from thot.tools.search.app import _load_pipeline_configuration
        >>> isinstance(_load_pipeline_configuration(), PipelineConfiguration)
        True
    """
    config = PipelineConfiguration()
    with open(
        os.path.join(configs_dir(), "pipeline.yaml"),
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
    configure_json_logging(service=os.getenv("TKEIR_SERVICE", "tkeir-api"))
    state = AppState()
    state.prompts = _load_prompts()
    state.llm = UnifiedLLMWrapper()
    state.vespa = VespaClient()
    state.pipeline_runners = await asyncio.to_thread(_load_pipeline_runners)
    if state.llm is not None:
        await state.llm.verify_provider(
            pull_missing=True,
            include_reranker=state.rag_config.search.rerank.enabled,
        )
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
# Outermost: correlation + observe-mode ActionRecords on every request.
app.add_middleware(ActionCorrelationMiddleware)
wire_governor_middleware(app, service=os.getenv("TKEIR_SERVICE", "tkeir-api"))


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


@app.get("/ready")
async def ready() -> dict:
    """Readiness probe: Vespa + configured PROVIDER endpoint.

    Returns HTTP 200 when both checks pass, otherwise 503.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(ready)
        True
    """
    state: AppState | None = getattr(app.state, "rag", None)
    vespa_ok = False
    llm = None
    if state is not None:
        llm = state.llm
        if state.vespa is not None:
            vespa_ok = await state.vespa.health()
    report = await readiness_report(vespa_ok=vespa_ok, llm=llm)
    if report["status"] != "ready":
        raise HTTPException(status_code=503, detail=report)
    return report


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus exposition of OpenTelemetry counters.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(metrics)
        True
    """
    ThotMetrics.create_counter(
        short_name="rag_http",
        function_name="tkeir_rag_http_requests_total",
        counter_description="RAG HTTP requests observed",
    )
    payload = ThotMetrics.generateMetricsResponse()
    return Response(
        content=payload,
        media_type=ThotMetrics.METRIC_MIME_TYPE,
    )


@app.get("/documents/analyzed")
async def get_analyzed_document(
    source_ref: str,
    analyzed_documents_path: str | None = None,
) -> dict[str, Any]:
    """Return one analyzed ingest document by ``source_ref``.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(get_analyzed_document)
        True
    """
    payload = _ingest_store_parent(
        source_ref,
        analyzed_documents_path=analyzed_documents_path,
    )
    if not payload:
        raise HTTPException(
            status_code=404,
            detail=f"No analyzed document found for source_ref={source_ref}",
        )
    return payload


@app.post("/business-ontology/parse")
async def parse_business_ontology_file(
    business_ontology: UploadFile = File(
        ...,
        description="business_ontology.yaml (or JSON) to parse",
    ),
) -> dict[str, Any]:
    """Parse an uploaded business ontology file into the concepts payload.

    Used by My-files basket brief / index so the same YAML can be passed as
    ``business_ontology`` on ``/search``, ``/rag/query``, and workspace index.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(parse_business_ontology_file)
        True
    """
    merged = await _parse_analyze_business_ontology_file(business_ontology)
    if merged is None:
        raise HTTPException(
            status_code=400,
            detail="Empty or invalid business_ontology file",
        )
    concepts = merged.get("concepts") if isinstance(merged, dict) else None
    return {
        "business_ontology": merged,
        "concept_count": len(concepts) if isinstance(concepts, list) else 0,
        "filename": getattr(business_ontology, "filename", None),
    }


@app.post("/documents/analyze")
async def analyze_document(
    file: UploadFile = File(..., description="Document bytes to analyze"),
    language: str = Form(default="en"),
    datatype: str = Form(
        default="raw",
        description="Converter datatype (default: raw UTF-8 text)",
    ),
    business_ontology: UploadFile | None = File(
        default=None,
        description=(
            "Optional business_ontology.yaml (or JSON) file to apply "
            "during analysis"
        ),
    ),
) -> dict[str, Any]:
    """Run converter + NLP pipeline on an uploaded file; return analyzed JSON.

    Does **not** index into Vespa. Default ``datatype=raw`` uses
    :class:`~thot.tasks.converters.RawTextConverter.RawTextConverter`.

    Optionally upload a ``business_ontology.yaml`` as multipart field
    ``business_ontology`` to annotate matched concepts onto the result.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(analyze_document)
        True
    """
    state: AppState = app.state.rag
    runner = _pipeline_runner_for_language(state, language)
    if runner is None:
        raise HTTPException(
            status_code=503,
            detail="Pipeline runners not initialized",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    filename = file.filename or "upload.txt"
    correlation_id = current_correlation_id() or new_action_id()
    resolved_datatype = (datatype or "raw").strip().lower() or "raw"
    bo_payload = await _parse_analyze_business_ontology_file(business_ontology)

    def _run() -> dict[str, Any]:
        """Run the ingest pipeline on uploaded bytes in a worker thread.

        Example:
            >>> True
            True
        """
        from thot.tools.ingest.worker import run_pipeline_on_bytes
        from thot.tools.search.business_ontology import (
            annotate_document_with_business_ontology,
        )

        analyzed = run_pipeline_on_bytes(
            runner,
            content,
            filename,
            correlation_id,
            datatype=resolved_datatype,
            document_extras={
                "source": f"upload://{correlation_id}/{filename}",
                "source_doc_id": f"upload://{correlation_id}/{filename}",
            },
        )
        if bo_payload:
            analyzed = annotate_document_with_business_ontology(
                analyzed, bo_payload
            )
            analyzed["business_ontology_applied"] = {
                "filename": getattr(business_ontology, "filename", None),
                "concept_count": len(bo_payload.get("concepts") or []),
            }
        return analyzed

    try:
        return await asyncio.to_thread(_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Document analyze failed for %s", filename)
        raise HTTPException(
            status_code=502,
            detail=f"Analyze failed: {exc}",
        ) from exc


async def _parse_analyze_business_ontology_file(
    business_ontology: UploadFile | None,
) -> dict[str, Any] | None:
    """Parse an uploaded ``business_ontology.yaml`` / JSON multipart file.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(_parse_analyze_business_ontology_file)
        True
    """
    import yaml

    from thot.tools.search.business_ontology import (
        merge_business_ontology_payloads,
    )

    if business_ontology is None:
        return None
    raw_bytes = await business_ontology.read()
    if not raw_bytes:
        return None
    text = raw_bytes.decode("utf-8", errors="replace")
    try:
        parsed = yaml.safe_load(text)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400,
            detail=f"Invalid business_ontology file: {exc}",
        ) from exc
    merged = merge_business_ontology_payloads(parsed)
    if merged is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "business_ontology file must contain a concepts list "
                "(YAML/JSON like business_ontology.yaml)"
            ),
        )
    return merged


def _extract_ranking_profile(
    vespa_payload: Any,
    query_analysis: Any,
) -> str | None:
    """Resolve ranking profile from Vespa payload or query analysis.

    Example:
        >>> _extract_ranking_profile({"ranking": {"profile": "hybrid"}}, None)
        'hybrid'
    """
    ranking_profile = None
    if isinstance(vespa_payload, dict):
        ranking_profile = vespa_payload.get("ranking.profile") or (
            vespa_payload.get("ranking")
            if isinstance(vespa_payload.get("ranking"), str)
            else None
        )
        if ranking_profile is None and isinstance(
            vespa_payload.get("ranking"), dict
        ):
            ranking_profile = vespa_payload["ranking"].get("profile")
    if ranking_profile is None and isinstance(query_analysis, dict):
        ranking_profile = query_analysis.get("ranking_profile")
    return str(ranking_profile) if ranking_profile else None


def _build_search_chunks(
    retrieved_chunks: list[RetrievedChunk],
    parsed_hits: list[tuple[dict[str, Any], float | None]],
) -> list[SearchChunk]:
    """Build SearchChunk list from retrieved chunks and hit titles.

    Example:
        >>> from thot.tools.search.app import RetrievedChunk, _build_search_chunks
        >>> chunks = [
        ...     RetrievedChunk(
        ...         chunk_id="c1", text_raw="t", parent_doc_id="d1", relevance=0.9
        ...     )
        ... ]
        >>> _build_search_chunks(chunks, [({"chunk_id": "c1", "title": "T"}, 0.9)])[0].title
        'T'
    """
    title_by_chunk = {
        str(fields.get("chunk_id") or ""): (
            str(
                fields.get("title") or fields.get("parent_title") or ""
            ).strip()
        )
        for fields, _ in parsed_hits
    }
    return [
        SearchChunk(
            chunk_id=chunk.chunk_id,
            text_raw=chunk.text_raw,
            parent_doc_id=chunk.parent_doc_id,
            score=float(chunk.relevance or 0.0),
            title=chunk.title or title_by_chunk.get(chunk.chunk_id, ""),
        )
        for chunk in retrieved_chunks
    ]


def _assemble_search_response(
    *,
    query_text: str,
    search_chunks: list[SearchChunk],
    parsed_hits: list[tuple[dict[str, Any], float | None]],
    ranking_profile: str | None,
    ontology: FusedOntology,
    query_ontology: FusedOntology | None = None,
    merged_ontology: FusedOntology | None = None,
    timings: SearchTimings | None = None,
) -> SearchResponse:
    """Aggregate chunks into documents and build SearchResponse.

    Example:
        >>> from thot.tools.search.app import (
        ...     FusedOntology,
        ...     SearchChunk,
        ...     _assemble_search_response,
        ... )
        >>> resp = _assemble_search_response(
        ...     query_text="q",
        ...     search_chunks=[
        ...         SearchChunk(
        ...             chunk_id="c1",
        ...             text_raw="t",
        ...             parent_doc_id="d1",
        ...             score=0.9,
        ...         )
        ...     ],
        ...     parsed_hits=[({"chunk_id": "c1"}, 0.9)],
        ...     ranking_profile="hybrid",
        ...     ontology=FusedOntology(entities=[], keywords=[]),
        ... )
        >>> resp.vespa_hits
        1
    """
    aggregated = aggregate_chunks_to_documents(
        [
            {
                "document_id": chunk.parent_doc_id,
                "chunk_id": chunk.chunk_id,
                "score": chunk.score,
                "title": chunk.title,
            }
            for chunk in search_chunks
        ]
    )
    return SearchResponse(
        query=query_text,
        chunks=search_chunks,
        documents=[
            SearchDocument(
                document_id=doc.document_id,
                score=doc.score,
                chunk_ids=doc.chunk_ids,
                title=doc.title,
                hit_count=doc.hit_count,
            )
            for doc in aggregated
        ],
        vespa_hits=len(parsed_hits),
        ranking_profile=ranking_profile,
        ontology=ontology,
        query_ontology=query_ontology,
        merged_ontology=merged_ontology,
        timings=timings,
    )


@app.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    authorization: str | None = Header(default=None),
) -> SearchResponse:
    """Hybrid retrieval + rerank without LLM answer generation.

    Returns reranked chunks and documents aggregated from those chunks
    (``max(chunk_score) + 0.05 * log1p(hit_count)``).

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(search)
        True
    """
    state: AppState = app.state.rag
    if state.llm is None or state.vespa is None:
        raise HTTPException(
            status_code=503, detail="Application is not initialized"
        )

    user_space = resolve_vespa_user_space(authorization)
    query_text = request.query.strip()
    request_started = time.perf_counter()
    source_refs = _normalize_source_refs(request.source_refs)
    search_mode = _resolve_search_mode_for_refs(
        request.search_mode, source_refs
    )
    retrieve_hits = _retrieve_hits_budget(request.hits, source_refs)
    business_ontology_payload = _resolve_request_business_ontology(
        state,
        business_ontology=request.business_ontology,
        business_ontology_dataset=request.business_ontology_dataset,
    )
    try:
        (
            search_response,
            vespa_payload,
            query_analysis,
            _,
        ) = await _retrieve_and_rerank(
            state,
            query_text=query_text,
            language=request.language,
            hits=retrieve_hits,
            user_space=user_space,
            business_ontology=business_ontology_payload,
            search_mode=search_mode,
        )
        parsed_hits = _filter_hits_by_source_refs(
            _parse_hits(search_response),
            source_refs,
        )[: request.hits]
        retrieved_chunks, rdf_payloads = await _enrich_hits(
            state,
            parsed_hits,
            analyzed_documents_path=request.analyzed_documents_path,
        )
        if source_refs:
            rdf_payloads = _merge_rdf_payload_lists(
                rdf_payloads,
                _collect_source_ref_rdf_payloads(
                    source_refs,
                    analyzed_documents_path=request.analyzed_documents_path,
                ),
            )
    except Exception as error:
        LOGGER.exception("Search failed")
        raise HTTPException(
            status_code=502, detail=f"Search failed: {error}"
        ) from error

    search_chunks = _build_search_chunks(retrieved_chunks, parsed_hits)
    ranking_profile = _extract_ranking_profile(vespa_payload, query_analysis)

    # Global = all retrieved parent/chunk document ontologies (not full BO dump).
    ontology = _fuse_response_ontology(
        state,
        rdf_payloads=rdf_payloads,
        retrieved_chunks=retrieved_chunks,
        business_ontology_payload=business_ontology_payload,
        ontology_json_ld=request.ontology_json_ld,
        document_ids=source_refs or None,
        include_full_business_ontology=False,
        analyzed_documents_path=request.analyzed_documents_path,
    )
    query_ontology = _build_query_ontology(
        state,
        query_text=query_text,
        language=request.language,
        query_analysis=(
            query_analysis if isinstance(query_analysis, dict) else None
        ),
        business_ontology_payload=business_ontology_payload,
    )
    query_ld = (query_ontology.json_ld or "").strip()
    merged_docs = list(rdf_payloads)
    if query_ld and query_ld != "[]":
        merged_docs.append(query_ld)
    extra_ld = (request.ontology_json_ld or "").strip()
    if extra_ld:
        merged_docs.append(extra_ld)
    merged_ontology = _fuse_response_ontology(
        state,
        rdf_payloads=merged_docs,
        retrieved_chunks=retrieved_chunks,
        ontology_json_ld=None,
        document_ids=(source_refs or []) + ["query://search"],
        include_full_business_ontology=False,
        analyzed_documents_path=request.analyzed_documents_path,
    )
    ontology = _attach_proposed_queries(
        ontology,
        query=query_text,
        query_analysis=(
            query_analysis if isinstance(query_analysis, dict) else None
        ),
    )
    merged_ontology = _attach_proposed_queries(
        merged_ontology,
        query=query_text,
        query_analysis=(
            query_analysis if isinstance(query_analysis, dict) else None
        ),
    )
    dual_timings = None
    if isinstance(query_analysis, dict):
        dual = query_analysis.get("dual_hybrid") or {}
        if isinstance(dual, dict):
            dual_timings = dual.get("timings_ms")
    timings = _timings_from_dual_ms(
        dual_timings if isinstance(dual_timings, dict) else None,
        total_ms=(time.perf_counter() - request_started) * 1000,
    )
    response = _assemble_search_response(
        query_text=query_text,
        search_chunks=search_chunks,
        parsed_hits=parsed_hits,
        ranking_profile=ranking_profile,
        ontology=ontology,
        query_ontology=query_ontology,
        merged_ontology=merged_ontology,
        timings=timings,
    )

    # Passage retrieval already logs stage timings inside PassageRetrievalPipeline.
    if not (isinstance(dual_timings, dict) and dual_timings):
        _log_search_timings(
            timings,
            query=query_text,
            ranking_profile=ranking_profile,
        )
    _log_rag_step(
        "search-total",
        request_started,
        query=repr(query_text),
        chunks=len(response.chunks),
        documents=len(response.documents),
        ontology_triples=ontology.triple_count,
        correlation_id=current_correlation_id() or "",
    )
    return response


@app.post("/rag/ontology/query", response_model=OntologyReasonerResponse)
async def ontology_reasoner_query(
    request: OntologyReasonerRequest,
) -> OntologyReasonerResponse:
    """Query the fused ontology returned by ``/search`` or ``/rag/query``.

    Pass the previous response's ``ontology.json_ld`` and choose an operation
    (SPARQL, subclasses, instances, types, consistency, expression, …).
    Uses the single pure-Python reasoner. Optionally re-merge
    ``business_ontology_dataset`` so follow-up queries see the same BO.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(ontology_reasoner_query)
        True
    """
    state: AppState = app.state.rag
    business_ontology_payload = _resolve_request_business_ontology(
        state,
        business_ontology=request.business_ontology,
        business_ontology_dataset=request.business_ontology_dataset,
    )
    extra_json_ld_raw = business_ontology_to_json_ld(business_ontology_payload)
    extra_json_ld: str | None = (
        None if extra_json_ld_raw == "[]" else extra_json_ld_raw
    )

    try:
        payload = query_merged_ontology(
            request.json_ld,
            operation=request.operation,
            class_iri=request.class_iri,
            individual_iri=request.individual_iri,
            sparql=request.sparql,
            expression=request.expression,
            reasoner=request.reasoner,
            direct=request.direct,
            limit=request.limit,
            extra_json_ld=extra_json_ld,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        LOGGER.exception("Ontology reasoner query failed")
        raise HTTPException(
            status_code=502,
            detail=f"Ontology reasoner query failed: {error}",
        ) from error

    return OntologyReasonerResponse(
        operation=str(payload.get("operation") or request.operation),
        backend=str(payload.get("backend") or "none"),
        reasoner=str(payload.get("reasoner") or request.reasoner),
        results=list(payload.get("results") or []),
        count=int(payload.get("count") or len(payload.get("results") or [])),
        consistent=payload.get("consistent"),
        triple_count=int(payload.get("triple_count") or 0),
        note=payload.get("note"),
        json_ld=payload.get("json_ld"),
        expression=request.expression
        or (
            str(payload.get("expression"))
            if payload.get("expression")
            else None
        ),
        sparql=(str(payload.get("sparql")) if payload.get("sparql") else None),
    )


def _select_prompt_rdf_payloads(
    rdf_payloads: list[str],
    retrieved_chunks: list[RetrievedChunk],
    prompt_chunks: list[RetrievedChunk],
) -> list[str]:
    """Keep RDF payloads aligned with chunks selected for prompt assembly.

    Example:
        >>> from thot.tools.search.app import RetrievedChunk, _select_prompt_rdf_payloads
        >>> chunks = [
        ...     RetrievedChunk(
        ...         chunk_id="c1", text_raw="t", parent_doc_id="d1"
        ...     )
        ... ]
        >>> _select_prompt_rdf_payloads(["<a>"], chunks, chunks)
        ['<a>']
    """
    prompt_chunk_ids = {chunk.chunk_id for chunk in prompt_chunks}
    prompt_rdf_payloads = [
        payload
        for payload, chunk in zip(rdf_payloads, retrieved_chunks, strict=False)
        if getattr(chunk, "chunk_id", None) in prompt_chunk_ids
    ]
    if not prompt_rdf_payloads:
        prompt_rdf_payloads = rdf_payloads[: len(prompt_chunks)]
    return prompt_rdf_payloads


def _maybe_supplement_entity_report_excerpts(
    *,
    chunk_excerpts: str,
    prompt_chunks: list[RetrievedChunk],
    prompt_cfg: dict[str, Any],
    query_text: str,
    query_analysis: dict[str, Any] | None,
    prompt_settings: RagPromptConfig,
    svo_only_prompt: bool,
) -> str:
    """Prepend source excerpts for entity-report queries in SVO-only mode.

    Example:
        >>> from thot.tools.search.app import _maybe_supplement_entity_report_excerpts
        >>> from thot.tools.search.rag_config import RagPromptConfig
        >>> _maybe_supplement_entity_report_excerpts(
        ...     chunk_excerpts="facts",
        ...     prompt_chunks=[],
        ...     prompt_cfg={},
        ...     query_text="hello",
        ...     query_analysis=None,
        ...     prompt_settings=RagPromptConfig("svo_ontology", 12),
        ...     svo_only_prompt=False,
        ... )
        'facts'
    """
    if not svo_only_prompt or not is_entity_report_query(
        query_text, query_analysis
    ):
        return chunk_excerpts
    supplement = _format_chunk_excerpts(
        prompt_chunks,
        empty_message="",
        max_chars_per_chunk=prompt_settings.max_chars_per_chunk,
        max_chunks=prompt_settings.max_chunks_for_prompt,
    )
    if not supplement.strip():
        return chunk_excerpts
    no_chunks_message = _no_chunks_message(prompt_cfg)
    if chunk_excerpts.strip() and chunk_excerpts != no_chunks_message:
        return (
            f"SOURCE EXCERPTS (read first for reports):\n{supplement}\n\n"
            f"STRUCTURED SVO FACTS:\n{chunk_excerpts}"
        )
    return supplement


def _build_rag_prompt_bundle(
    state: AppState,
    request: QueryRequest,
    *,
    retrieved_chunks: list[RetrievedChunk],
    rdf_payloads: list[str],
    query_text: str,
    query_analysis: dict[str, Any] | None,
    focus_query_text: str,
    query_analysis_context: str,
    svo_match_query: str,
    business_ontology_payload: dict[str, Any] | None = None,
) -> tuple[
    str,
    str,
    str,
    str,
    str,
    FusedOntology,
    str,
    list[RetrievedChunk],
]:
    """Build prompts, ontology, and generation inputs for ``rag_query``.

    Example:
        >>> from thot.tools.search.app import (
        ...     AppState,
        ...     QueryRequest,
        ...     _build_rag_prompt_bundle,
        ...     _load_prompts,
        ... )
        >>> state = AppState()
        >>> state.prompts = _load_prompts()
        >>> len(_build_rag_prompt_bundle(
        ...     state,
        ...     QueryRequest(query="hello"),
        ...     retrieved_chunks=[],
        ...     rdf_payloads=[],
        ...     query_text="hello",
        ...     query_analysis={},
        ...     focus_query_text="hello",
        ...     query_analysis_context="- terms: hello",
        ...     svo_match_query="hello",
        ... ))
        8
    """
    prompt_chunks = filter_query_relevant_chunks(
        retrieved_chunks,
        focus_query_text,
        max_chunks=state.rag_config.prompt.max_chunks_for_prompt,
    )
    prompt_rdf_payloads = _select_prompt_rdf_payloads(
        rdf_payloads,
        retrieved_chunks,
        prompt_chunks,
    )
    fused_graph = merge_rdf_graphs(prompt_rdf_payloads)
    svo_only_prompt = _uses_svo_only_prompt(state.rag_config.prompt)
    fused_summary = ""
    if not svo_only_prompt:
        fused_summary = summarize_graph_for_prompt(
            fused_graph,
            svo_match_query,
            max_triples=_DEFAULT_MAX_TRIPLES_FOR_PROMPT,
        )
    ontology = _fuse_response_ontology(
        state,
        rdf_payloads=rdf_payloads,
        retrieved_chunks=retrieved_chunks,
        business_ontology_payload=business_ontology_payload,
        ontology_json_ld=request.ontology_json_ld,
        document_ids=_normalize_source_refs(request.source_refs) or None,
        analyzed_documents_path=request.analyzed_documents_path,
    )
    ontology = _attach_proposed_queries(
        ontology,
        query=query_text,
        query_analysis=(
            query_analysis if isinstance(query_analysis, dict) else None
        ),
    )

    prompt_cfg = _language_prompt_cfg(state.prompts, request.language)
    unavailable_answer = _unavailable_answer(prompt_cfg, request.language)
    user_prompt_template = _resolve_user_prompt_template(
        prompt_cfg,
        state.rag_config.prompt,
    )
    system_prompt_template = _resolve_system_prompt_template(
        prompt_cfg,
        state.rag_config.prompt,
    )
    chunk_excerpts = _format_chunk_context(
        prompt_settings=state.rag_config.prompt,
        graph=fused_graph,
        query_text=svo_match_query,
        chunks=prompt_chunks,
        empty_message=_no_chunks_message(prompt_cfg),
        max_chars_per_chunk=state.rag_config.prompt.max_chars_per_chunk,
        max_chunks=state.rag_config.prompt.max_chunks_for_prompt,
    )
    passage_settings = resolve_passage_settings(
        defaults=state.rag_config.prompt.passages,
        count=request.max_passages,
        max_chars=request.max_chars_per_passage,
        context_sentences=request.focus_context_sentences,
    )
    focus_passages = extract_focus_passages(
        [
            (chunk.chunk_id, clean_chunk_text_for_prompt(chunk.text_raw))
            for chunk in prompt_chunks
        ],
        focus_query_text,
        max_passages=passage_settings.count,
        context_sentences=passage_settings.context_sentences,
        max_chars_per_passage=passage_settings.max_chars,
        analysis=query_analysis,
    )
    # When SVO ontology context is empty but we have passages, inject chunk
    # excerpts so "what happened at X" questions still get narrative evidence.
    if svo_only_prompt and prompt_chunks:
        no_chunks_message = _no_chunks_message(prompt_cfg)
        if not chunk_excerpts.strip() or chunk_excerpts == no_chunks_message:
            chunk_excerpts = _format_chunk_excerpts(
                prompt_chunks,
                empty_message=no_chunks_message,
                max_chars_per_chunk=state.rag_config.prompt.max_chars_per_chunk,
                max_chunks=state.rag_config.prompt.max_chunks_for_prompt,
            )
    generation_guidance = format_generation_guidance(
        query_text,
        query_analysis,
        language=request.language,
    )
    chunk_excerpts = _maybe_supplement_entity_report_excerpts(
        chunk_excerpts=chunk_excerpts,
        prompt_chunks=prompt_chunks,
        prompt_cfg=prompt_cfg,
        query_text=query_text,
        query_analysis=query_analysis,
        prompt_settings=state.rag_config.prompt,
        svo_only_prompt=svo_only_prompt,
    )
    system_prompt, user_prompt = _build_generation_prompts(
        prompt_cfg,
        fused_summary=fused_summary,
        focus_passages=focus_passages,
        chunk_excerpts=chunk_excerpts,
        query_text=query_text,
        query_analysis=query_analysis_context,
        generation_guidance=generation_guidance,
        unavailable_answer=unavailable_answer,
        user_prompt_template=user_prompt_template,
        system_prompt_template=system_prompt_template,
    )
    input_prompt = format_input_prompt(system_prompt, user_prompt)
    return (
        system_prompt,
        user_prompt,
        input_prompt,
        focus_passages,
        chunk_excerpts,
        ontology,
        unavailable_answer,
        prompt_chunks,
    )


def _resolve_highlight_labels(
    *,
    state: AppState,
    ontology: FusedOntology,
    query_text: str,
    retrieved_chunks: list[RetrievedChunk],
    language: str,
    query_analysis: dict[str, Any] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Build entity / keyword / query highlight labels with NLP POS filtering.

    Example:
        >>> from thot.tools.search.app import (
        ...     AppState,
        ...     FusedOntology,
        ...     _resolve_highlight_labels,
        ... )
        >>> _resolve_highlight_labels(
        ...     state=AppState(),
        ...     ontology=FusedOntology(entities=[], keywords=[]),
        ...     query_text="hello",
        ...     retrieved_chunks=[],
        ...     language="en",
        ... )
        ([], [], ['hello'])
    """
    from thot.tools.search.query_analyzer import (
        content_terms_from_morphosyntax,
    )

    analysis = query_analysis if isinstance(query_analysis, dict) else {}
    morph = analysis.get("morphosyntax")
    morph_list = morph if isinstance(morph, list) else None
    content_terms = (
        content_terms_from_morphosyntax(morph_list) if morph_list else set()
    )
    runner = _pipeline_runner_for_language(state, language)
    entity_labels, keyword_labels = extract_highlight_labels(
        ontology,
        morphosyntax=morph_list,
        content_terms=content_terms or None,
        pipeline_runner=runner,
    )
    query_term_labels = query_highlight_terms(
        query_text,
        retrieved_chunks,
        content_terms=content_terms or None,
        morphosyntax=morph_list,
    )
    return entity_labels, keyword_labels, query_term_labels


def _build_rag_unavailable_response(
    *,
    state: AppState,
    query_text: str,
    request: QueryRequest,
    retrieved_chunks: list[RetrievedChunk],
    parsed_hits: list[tuple[dict[str, Any], float | None]],
    ontology: FusedOntology,
    unavailable_answer: str,
    focus_passages: str,
    chunk_excerpts: str,
    input_prompt: str,
    vespa_query_json: str,
    step_started: float,
    request_started: float,
    query_analysis: dict[str, Any] | None = None,
) -> QueryResponse:
    """Return the standard unavailable response when retrieval is empty.

    Example:
        >>> import inspect
        >>> inspect.isfunction(_build_rag_unavailable_response)
        True
    """
    entity_labels, keyword_labels, query_term_labels = (
        _resolve_highlight_labels(
            state=state,
            ontology=ontology,
            query_text=query_text,
            retrieved_chunks=retrieved_chunks,
            language=request.language,
            query_analysis=query_analysis,
        )
    )
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
        input_prompt=input_prompt,
        vespa_query=vespa_query_json,
    )
    _log_rag_step(
        "answer-building",
        step_started,
        generated=False,
        chunks=len(retrieved_chunks),
    )
    _log_rag_step("rag-query-total", request_started, query=repr(query_text))
    return QueryResponse(
        answer=unavailable_answer,
        report_markdown=report_markdown,
        input_prompt=input_prompt,
        vespa_query=vespa_query_json,
        highlight_entities=entity_labels,
        highlight_keywords=keyword_labels,
        highlight_query_terms=query_term_labels,
        used_chunk_evidence=False,
        answer_unavailable=True,
        chunks=retrieved_chunks,
        ontology=ontology,
        vespa_hits=len(parsed_hits),
    )


async def _generate_rag_answer(
    state: AppState,
    *,
    user_prompt: str,
    system_prompt: str,
    query_text: str,
    prompt_chunks: list[RetrievedChunk],
    unavailable_answer: str,
    focus_passages: str,
    chunk_excerpts: str,
    language: str = "en",
    query_analysis: dict[str, Any] | None = None,
) -> tuple[str, str, bool]:
    """Run LLM generation and apply chunk-evidence fallback when needed.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(_generate_rag_answer)
        True
    """
    if state.llm is None:
        raise HTTPException(
            status_code=503, detail="Application is not initialized"
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
    analysis = query_analysis if isinstance(query_analysis, dict) else {}
    query_content_terms: set[str] = set()
    for key in ("lemmas", "search_terms"):
        for term in analysis.get(key) or []:
            cleaned = str(term).strip().lower()
            if cleaned:
                query_content_terms.add(cleaned)
    for entity in analysis.get("ner_entities") or []:
        if isinstance(entity, dict):
            cleaned = str(entity.get("text") or "").strip().lower()
        else:
            cleaned = str(entity or "").strip().lower()
        if cleaned:
            query_content_terms.add(cleaned)
    short_answer, detailed_report, used_chunk_evidence = (
        apply_chunk_evidence_fallback(
            query_text=query_text,
            short_answer=short_answer,
            detailed_report=detailed_report,
            chunks=prompt_chunks,
            unavailable_answer=unavailable_answer,
            language=language,
            pipeline_runner=_pipeline_runner_for_language(state, language),
            query_content_terms=query_content_terms or None,
        )
    )
    if not detailed_report.strip():
        detailed_report = build_fallback_detailed_report(
            focus_passages=focus_passages,
            chunk_excerpts=chunk_excerpts,
        )
    return short_answer, detailed_report, used_chunk_evidence


def _build_rag_success_response(
    *,
    state: AppState,
    query_text: str,
    request: QueryRequest,
    retrieved_chunks: list[RetrievedChunk],
    parsed_hits: list[tuple[dict[str, Any], float | None]],
    ontology: FusedOntology,
    unavailable_answer: str,
    input_prompt: str,
    vespa_query_json: str,
    short_answer: str,
    detailed_report: str,
    used_chunk_evidence: bool,
    query_analysis: dict[str, Any] | None = None,
) -> QueryResponse:
    """Build the successful ``QueryResponse`` after generation.

    Example:
        >>> from thot.tools.search.app import (
        ...     AppState,
        ...     FusedOntology,
        ...     QueryRequest,
        ...     _build_rag_success_response,
        ... )
        >>> resp = _build_rag_success_response(
        ...     state=AppState(),
        ...     query_text="hello",
        ...     request=QueryRequest(query="hello"),
        ...     retrieved_chunks=[],
        ...     parsed_hits=[],
        ...     ontology=FusedOntology(entities=[], keywords=[]),
        ...     unavailable_answer="N/A",
        ...     input_prompt="",
        ...     vespa_query_json="",
        ...     short_answer="answer",
        ...     detailed_report="detail",
        ...     used_chunk_evidence=False,
        ... )
        >>> resp.answer
        'answer'
    """
    entity_labels, keyword_labels, query_term_labels = (
        _resolve_highlight_labels(
            state=state,
            ontology=ontology,
            query_text=query_text,
            retrieved_chunks=retrieved_chunks,
            language=request.language,
            query_analysis=query_analysis,
        )
    )
    report_markdown = assemble_report_markdown(
        query=query_text,
        language=request.language,
        short_answer=short_answer,
        detailed_report=detailed_report,
        chunks=retrieved_chunks,
        ontology=ontology,
        vespa_hits=len(parsed_hits),
        input_prompt=input_prompt,
        vespa_query=vespa_query_json,
    )
    return QueryResponse(
        answer=short_answer,
        report_markdown=report_markdown,
        input_prompt=input_prompt,
        vespa_query=vespa_query_json,
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


@app.post("/rag/query", response_model=QueryResponse)
async def rag_query(
    request: QueryRequest,
    authorization: str | None = Header(default=None),
) -> QueryResponse:
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

    user_space = resolve_vespa_user_space(authorization)
    query_text = request.query.strip()
    request_started = time.perf_counter()
    source_refs = _normalize_source_refs(request.source_refs)
    search_mode = _resolve_search_mode_for_refs(
        request.search_mode, source_refs
    )
    retrieve_hits = _retrieve_hits_budget(request.hits, source_refs)
    business_ontology_payload = _resolve_request_business_ontology(
        state,
        business_ontology=request.business_ontology,
        business_ontology_dataset=request.business_ontology_dataset,
    )

    step_started = time.perf_counter()
    try:
        (
            search_response,
            vespa_payload,
            query_analysis,
            search_query_text,
        ) = await _retrieve_and_rerank(
            state,
            query_text=query_text,
            language=request.language,
            hits=retrieve_hits,
            user_space=user_space,
            business_ontology=business_ontology_payload,
            search_mode=search_mode,
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
        analyzer=bool(query_analysis),
    )

    vespa_query_json = (
        format_vespa_query_json(vespa_payload) if vespa_payload else ""
    )
    svo_match_query = build_svo_match_query(
        raw_query=query_text,
        lexical_query=search_query_text,
        analysis=query_analysis,
    )
    focus_query_text = build_focus_query_text(
        raw_query=query_text,
        analysis=query_analysis,
    )
    query_analysis_context = format_query_analysis_for_prompt(
        raw_query=query_text,
        lexical_query=search_query_text,
        analysis=query_analysis,
    )

    step_started = time.perf_counter()
    try:
        parsed_hits = _filter_hits_by_source_refs(
            _parse_hits(search_response),
            source_refs,
        )[: request.hits]
        retrieved_chunks, rdf_payloads = await _enrich_hits(
            state,
            parsed_hits,
            analyzed_documents_path=request.analyzed_documents_path,
        )
        if source_refs:
            rdf_payloads = _merge_rdf_payload_lists(
                rdf_payloads,
                _collect_source_ref_rdf_payloads(
                    source_refs,
                    analyzed_documents_path=request.analyzed_documents_path,
                ),
            )
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
        focus_query_text,
    )

    step_started = time.perf_counter()
    (
        system_prompt,
        user_prompt,
        input_prompt,
        focus_passages,
        chunk_excerpts,
        ontology,
        unavailable_answer,
        prompt_chunks,
    ) = _build_rag_prompt_bundle(
        state,
        request,
        retrieved_chunks=retrieved_chunks,
        rdf_payloads=rdf_payloads,
        query_text=query_text,
        query_analysis=query_analysis,
        focus_query_text=focus_query_text,
        query_analysis_context=query_analysis_context,
        svo_match_query=svo_match_query,
        business_ontology_payload=business_ontology_payload,
    )

    if not retrieved_chunks:
        return _build_rag_unavailable_response(
            state=state,
            query_text=query_text,
            request=request,
            retrieved_chunks=retrieved_chunks,
            parsed_hits=parsed_hits,
            ontology=ontology,
            unavailable_answer=unavailable_answer,
            focus_passages=focus_passages,
            chunk_excerpts=chunk_excerpts,
            input_prompt=input_prompt,
            vespa_query_json=vespa_query_json,
            step_started=step_started,
            request_started=request_started,
            query_analysis=(
                query_analysis if isinstance(query_analysis, dict) else None
            ),
        )

    (
        short_answer,
        detailed_report,
        used_chunk_evidence,
    ) = await _generate_rag_answer(
        state,
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        query_text=query_text,
        prompt_chunks=prompt_chunks,
        unavailable_answer=unavailable_answer,
        focus_passages=focus_passages,
        chunk_excerpts=chunk_excerpts,
        language=request.language,
        query_analysis=query_analysis,
    )

    _log_rag_step(
        "answer-building",
        step_started,
        generated=True,
        chunks=len(retrieved_chunks),
    )
    _log_rag_step("rag-query-total", request_started, query=repr(query_text))

    return _build_rag_success_response(
        state=state,
        query_text=query_text,
        request=request,
        retrieved_chunks=retrieved_chunks,
        parsed_hits=parsed_hits,
        ontology=ontology,
        unavailable_answer=unavailable_answer,
        input_prompt=input_prompt,
        vespa_query_json=vespa_query_json,
        short_answer=short_answer,
        detailed_report=detailed_report,
        used_chunk_evidence=used_chunk_evidence,
        query_analysis=(
            query_analysis if isinstance(query_analysis, dict) else None
        ),
    )


def main() -> None:
    """CLI entry point for the RAG FastAPI server.

    Example:
        >>> from thot.tools.search import app as rag_app
        >>> callable(rag_app.main)
        True
    """
    import uvicorn

    from thot.core.StructuredLogging import configure_text_logging

    configure_text_logging(level=logging.INFO, force=True)
    uvicorn.run(
        "thot.tools.search.app:app",
        host=os.getenv("RAG_HOST", "0.0.0.0"),
        port=int(os.getenv("RAG_PORT", "8090")),
        reload=False,
    )


if __name__ == "__main__":
    main()
