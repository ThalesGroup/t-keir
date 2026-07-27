"""Title: Query analyzer

Run the NLP pipeline on user queries and build Vespa search payloads.
Generation / LLM prompt formatting lives in ``generation_prompt``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from thot.core.ThotLogger import ThotLogger
from thot.tasks.pipeline.PipelineRunner import PipelineRunner
from thot.tools.search.query_refiner import meaningful_tokens_from_morphosyntax
from thot.tools.search.rag_config import RagSearchConfig
from thot.tools.search.vespa_client import (
    build_chunk_tensor,
    build_field_contains_or_clause,
    build_multi_field_contains_or_clause,
)

_WHITESPACE_RE = re.compile(r"\s+")
_RELATION_PREFIX = "rel:"


class EmbeddingClient(Protocol):
    """Minimal async embedding client interface."""

    async def embed(self, text: str) -> list[float]:
        """Embed text into a dense vector.

        Example:
            >>> import inspect
            >>> from thot.tools.search.query_analyzer import EmbeddingClient
            >>> inspect.isabstract(EmbeddingClient.embed)
            False
        """
        ...


@dataclass(frozen=True)
class NerEntity:
    text: str
    label: str


@dataclass(frozen=True)
class SvoTriple:
    subject: str
    verb: str
    object: str


@dataclass
class QueryAnalysis:
    """Structured output of the linguistic query pipeline."""

    raw_query: str
    language: str | None
    ner_entities: list[NerEntity] = field(default_factory=list)
    svo_triples: list[SvoTriple] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    lemmas: list[str] = field(default_factory=list)
    search_terms: list[str] = field(default_factory=list)
    lexical_query: str = ""
    chunk_embedding_text: str = ""
    pipeline_failed: bool = False


def _node_text(node: dict[str, Any] | None) -> str:
    """Extract display text from a pipeline graph node.

    Example:
        >>> from thot.tools.search.query_analyzer import _node_text
        >>> _node_text({"content": "Microsoft"})
        'Microsoft'
    """
    if not node:
        return ""
    content = node.get("content")
    if isinstance(content, list):
        return " ".join(
            str(part).strip() for part in content if str(part).strip()
        )
    if isinstance(content, str):
        return content.strip()
    lemma = node.get("lemma_content")
    if isinstance(lemma, list):
        return " ".join(
            str(part).strip() for part in lemma if str(part).strip()
        )
    if isinstance(lemma, str):
        return lemma.strip()
    return ""


def extract_ner_entities(ner_spans: list[dict[str, Any]]) -> list[NerEntity]:
    """Extract named entities from pipeline NER spans.

    Example:
        >>> extract_ner_entities([{"text": "Microsoft", "label": "organization"}])
        [NerEntity(text='Microsoft', label='organization')]
    """
    entities: list[NerEntity] = []
    seen: set[tuple[str, str]] = set()
    for span in ner_spans or []:
        text = str(span.get("text", "")).strip()
        label = str(span.get("label", "entity")).strip() or "entity"
        if not text:
            continue
        key = (text.lower(), label.lower())
        if key in seen:
            continue
        seen.add(key)
        entities.append(NerEntity(text=text, label=label))
    return entities


def extract_svo_triples(kg_triples: list[dict[str, Any]]) -> list[SvoTriple]:
    """Extract subject-verb-object triples from pipeline ``kg`` output.

    Example:
        >>> triples = [{
        ...     "subject": {"content": "Microsoft"},
        ...     "property": {"content": "acquire"},
        ...     "value": {"content": "GitHub"},
        ... }]
        >>> extract_svo_triples(triples)[0].subject
        'Microsoft'
    """
    triples: list[SvoTriple] = []
    seen: set[tuple[str, str, str]] = set()
    for triple in kg_triples or []:
        subject = _node_text(triple.get("subject"))
        verb = _node_text(triple.get("property"))
        obj = _node_text(triple.get("value"))
        if verb.startswith(_RELATION_PREFIX):
            continue
        if not subject and not verb and not obj:
            continue
        key = (subject.lower(), verb.lower(), obj.lower())
        if key in seen:
            continue
        seen.add(key)
        triples.append(SvoTriple(subject=subject, verb=verb, object=obj))
    return triples


def extract_keyword_terms(keywords: list[dict[str, Any]]) -> list[str]:
    """Extract keyword texts ordered by salience score.

    Example:
        >>> extract_keyword_terms([{"text": "cloud platform", "score": 10}])
        ['cloud platform']
    """
    ranked = sorted(
        keywords or [],
        key=lambda item: int(item.get("score") or 0),
        reverse=True,
    )
    terms: list[str] = []
    seen: set[str] = set()
    for item in ranked:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(text)
    return terms


# Universal Dependencies content POS tags (language-agnostic).
_CONTENT_POS = frozenset({"NOUN", "PROPN", "VERB", "ADJ", "NUM"})


def extract_lemma_terms(morphosyntax: list[dict[str, Any]]) -> list[str]:
    """Extract content-bearing lemmas from morphosyntax (UD POS filter).

    Example:
        >>> morph = [
        ...     {"text": "the", "lemma": "the", "pos": "DET"},
        ...     {"text": "acquired", "lemma": "acquire", "pos": "VERB"},
        ... ]
        >>> extract_lemma_terms(morph)
        ['acquire']
    """
    lemmas: list[str] = []
    seen: set[str] = set()
    for token in morphosyntax or []:
        pos = str(token.get("pos") or "").upper()
        if pos and pos not in _CONTENT_POS:
            continue
        lemma = str(token.get("lemma") or token.get("text") or "").strip()
        if not lemma:
            continue
        key = lemma.lower()
        if key in seen:
            continue
        seen.add(key)
        lemmas.append(lemma)
    return lemmas


def build_search_terms(
    analysis: QueryAnalysis, config: RagSearchConfig
) -> list[str]:
    """Merge NER, SVO, keywords, and lemmas into a deduplicated term list.

    Example:
        >>> analysis = QueryAnalysis(
        ...     raw_query="test",
        ...     language="en",
        ...     ner_entities=[NerEntity("Microsoft", "organization")],
        ...     lemmas=["acquire"],
        ... )
        >>> build_search_terms(analysis, RagSearchConfig())[0]
        'Microsoft'
    """
    ordered: list[str] = []
    seen: set[str] = set()

    def add_term(value: str) -> None:
        cleaned = (value or "").strip()
        if not cleaned:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        ordered.append(cleaned)

    if config.use_ner:
        for entity in analysis.ner_entities:
            add_term(entity.text)

    if config.use_svo:
        for triple in analysis.svo_triples:
            add_term(triple.subject)
            add_term(triple.verb)
            add_term(triple.object)

    if config.use_keywords:
        for keyword in analysis.keywords:
            add_term(keyword)

    if config.use_lemmas:
        for lemma in analysis.lemmas:
            add_term(lemma)

    if not ordered:
        for token in meaningful_tokens_from_morphosyntax(
            [
                {"text": part, "pos": "X"}
                for part in _WHITESPACE_RE.split(analysis.raw_query)
                if part
            ]
        ):
            add_term(token)
        if not ordered:
            for part in _WHITESPACE_RE.split(analysis.raw_query):
                add_term(part)

    return ordered[: config.max_yql_terms]


def build_chunk_embedding_text(analysis: QueryAnalysis) -> str:
    """Build the query string for dense embedding (``q_dense``).

    Prefer the raw query so paraphrase / stance mismatch still embeds; fall
    back to the lexical projection when the raw string is empty.

    Example:
        >>> analysis = QueryAnalysis(
        ...     raw_query="What did Microsoft acquire?",
        ...     language="en",
        ...     lexical_query="Microsoft acquire",
        ... )
        >>> build_chunk_embedding_text(analysis)
        'What did Microsoft acquire?'
    """
    return (analysis.raw_query or analysis.lexical_query or "").strip()


def select_ranking_profile(analysis: QueryAnalysis) -> str:
    """Choose a Vespa rank profile from structural query signals.

    Uses only counts derived from NLP output (NER / lemmas / SVO / terms) —
    no language-specific word lists.

    Args:
        analysis: Query analysis from the linguistic pipeline.

    Returns:
        Vespa rank profile name (``hybrid`` on ``global`` / ``user`` schemas).

    Example:
        >>> select_ranking_profile(QueryAnalysis(
        ...     raw_query="x", language="en",
        ...     ner_entities=[NerEntity("Microsoft", "ORG")],
        ...     search_terms=["Microsoft"],
        ... ))
        'hybrid'
    """
    del analysis  # Signals reserved for future profile variants.
    return "hybrid"


def build_hybrid_yql(
    analysis: QueryAnalysis,
    config: RagSearchConfig,
    *,
    hits: int,
) -> str:
    """Assemble the YQL query for hybrid chunk retrieval.

    Example:
        >>> analysis = QueryAnalysis(
        ...     raw_query="Microsoft acquire",
        ...     language="en",
        ...     search_terms=["Microsoft", "acquire"],
        ... )
        >>> yql = build_hybrid_yql(analysis, RagSearchConfig(use_chunk_embedding=False), hits=5)
        >>> "Microsoft" in yql
        True
    """
    yql_parts: list[str] = []
    if config.use_chunk_embedding:
        yql_parts.append(
            f'([{{"targetNumHits": {hits}}}]nearestNeighbor(dense_vector, q_dense))'
        )

    bm25_fields: list[str] = []
    if config.use_text_raw:
        bm25_fields.append("chunk_text")

    if bm25_fields and analysis.search_terms:
        text_clause = build_multi_field_contains_or_clause(
            analysis.search_terms,
            fields=tuple(bm25_fields),
        )
        if text_clause:
            yql_parts.append(text_clause)

    if not yql_parts:
        fallback = build_field_contains_or_clause(
            "chunk_text", analysis.raw_query
        )
        if fallback:
            yql_parts.append(fallback)
        else:
            yql_parts.append("true")

    return "select * from user where " + " or ".join(yql_parts)


def build_vespa_search_payload(
    analysis: QueryAnalysis,
    config: RagSearchConfig,
    *,
    q_dense: list[float],
    hits: int,
    timeout_seconds: float,
    embedding_dim: int,
    user_space: str | None = None,
) -> dict[str, Any]:
    """Build a Vespa HTTP search payload from analysis and embeddings.

    Example:
        >>> analysis = QueryAnalysis(raw_query="Microsoft", language="en", search_terms=["Microsoft"])
        >>> payload = build_vespa_search_payload(
        ...     analysis,
        ...     RagSearchConfig(),
        ...     q_dense=[0.0] * 1024,
        ...     hits=10,
        ...     timeout_seconds=30.0,
        ...     embedding_dim=1024,
        ...     user_space="demo",
        ... )
        >>> payload["ranking.profile"]
        'hybrid'
        >>> payload["streaming.groupname"]
        'demo'
    """
    profile = (config.ranking_profile or "auto").strip()
    if profile == "auto":
        profile = select_ranking_profile(analysis)
    # Legacy profile names → current schema profile.
    if profile in {"hybrid_2_level", "hybrid_semantic", "hybrid_lexical"}:
        profile = "hybrid"
    payload: dict[str, Any] = {
        "yql": build_hybrid_yql(analysis, config, hits=hits),
        "hits": hits,
        "timeout": f"{int(timeout_seconds)}s",
        "ranking.profile": profile,
    }
    from thot.tools.search.vespa_client import normalize_user_space

    payload["streaming.groupname"] = normalize_user_space(user_space)
    if config.use_chunk_embedding:
        payload["input.query(q_dense)"] = build_chunk_tensor(
            q_dense,
            embedding_dim=embedding_dim,
        )
    return payload


def build_svo_match_query(
    *,
    raw_query: str,
    lexical_query: str,
    analysis: dict[str, Any] | None = None,
) -> str:
    """Build a query string optimized for SVO proximity matching.

    Example:
        >>> build_svo_match_query(
        ...     raw_query="What did Microsoft acquire?",
        ...     lexical_query="Microsoft acquire",
        ...     analysis={
        ...         "svo_triples": [{"subject": "Microsoft", "verb": "acquire", "object": ""}],
        ...         "search_terms": ["Microsoft", "acquire"],
        ...     },
        ... )
        'Microsoft acquire'
    """
    parts: list[str] = []
    if analysis:
        for triple in analysis.get("svo_triples") or []:
            for key in ("subject", "verb", "object"):
                value = str(triple.get(key, "")).strip()
                if value:
                    parts.append(value)
        for term in analysis.get("search_terms") or []:
            text = str(term).strip()
            if text:
                parts.append(text)
    if parts:
        return " ".join(dict.fromkeys(parts))
    return (lexical_query or raw_query).strip()


_VESPA_EMBEDDING_KEYS = (
    "input.query(q_dense)",
    "input.query(q_sparse)",
)


def format_vespa_query_json(payload: dict[str, Any]) -> str:
    """Serialize a Vespa search payload as pretty-printed JSON.

    Embedding vectors are omitted from the API/report payload to keep
    responses compact.

    Example:
        >>> rendered = format_vespa_query_json({
        ...     "yql": "select * from user where true",
        ...     "input.query(q_dense)": [0.1, 0.2],
        ... })
        >>> '"omitted": true' in rendered
        True
    """
    display = dict(payload)
    for key in _VESPA_EMBEDDING_KEYS:
        if key not in display:
            continue
        vector = display[key]
        if isinstance(vector, list):
            display[key] = {"omitted": True, "dimensions": len(vector)}
    return json.dumps(display, indent=2, ensure_ascii=False)


def run_linguistic_pipeline(
    runner: PipelineRunner,
    raw_query: str,
    *,
    language: str | None = None,
) -> dict[str, Any]:
    """Run tokenizer, morphosyntax, NER, syntax, and keywords on a query.

    Example:
        >>> callable(run_linguistic_pipeline)
        True
    """
    document: dict[str, Any] = {"content": [raw_query.strip()]}
    if language:
        document["language-detection"] = {"language": language}
    return runner.run(
        document,
        skip_converter=True,
        tasks=["ner", "syntax", "keywords"],
    )


def analyze_query_document(
    processed: dict[str, Any],
    raw_query: str,
    *,
    language: str | None,
    config: RagSearchConfig,
) -> QueryAnalysis:
    """Convert pipeline output into a :class:`QueryAnalysis`.

    Example:
        >>> analysis = analyze_query_document({}, "Microsoft acquire", language="en", config=RagSearchConfig())
        >>> analysis.raw_query
        'Microsoft acquire'
    """
    morphosyntax = processed.get("content_morphosyntax") or []
    analysis = QueryAnalysis(
        raw_query=raw_query,
        language=language,
        ner_entities=extract_ner_entities(processed.get("content_ner") or []),
        svo_triples=extract_svo_triples(processed.get("kg") or []),
        keywords=extract_keyword_terms(processed.get("keywords") or []),
        lemmas=extract_lemma_terms(morphosyntax),
    )
    if not analysis.lemmas:
        analysis.lemmas = meaningful_tokens_from_morphosyntax(morphosyntax)
    analysis.search_terms = build_search_terms(analysis, config)
    analysis.lexical_query = " ".join(analysis.search_terms)
    analysis.chunk_embedding_text = build_chunk_embedding_text(analysis)
    return analysis


class QueryAnalyzerTask:
    """Analyze a raw query and produce a Vespa hybrid search payload."""

    def __init__(
        self,
        runner: PipelineRunner,
        llm: EmbeddingClient,
        config: RagSearchConfig,
        *,
        embedding_dim: int = 384,
        timeout_seconds: float = 60.0,
        user_space: str | None = None,
    ):
        """Initialize the analyzer with pipeline, embedder, and search config.

        Example:
            >>> callable(QueryAnalyzerTask)
            True
        """
        from thot.tools.search.vespa_client import normalize_user_space

        self._runner = runner
        self._llm = llm
        self._config = config
        self._embedding_dim = embedding_dim
        self._timeout_seconds = timeout_seconds
        self._user_space = normalize_user_space(user_space)

    @property
    def config(self) -> RagSearchConfig:
        """Return the active search configuration.

        Example:
            >>> class _LLM:
            ...     async def embed(self, text):
            ...         return [0.0] * 384
            >>> task = QueryAnalyzerTask(None, _LLM(), RagSearchConfig())  # doctest: +SKIP
            >>> task.config.ranking_profile  # doctest: +SKIP
            'auto'
        """
        return self._config

    def analyze_sync(
        self,
        raw_query: str,
        *,
        language: str | None = None,
    ) -> QueryAnalysis:
        """Run the linguistic pipeline synchronously.

        Example:
            >>> callable(QueryAnalyzerTask.analyze_sync)
            True
        """
        normalized = (raw_query or "").strip()
        if not normalized:
            return QueryAnalysis(raw_query=raw_query, language=language)

        try:
            processed = run_linguistic_pipeline(
                self._runner,
                normalized,
                language=language,
            )
        except Exception as error:
            ThotLogger.warning(
                "QueryAnalyzerTask pipeline failed; using lexical fallback",
                trace=str(error),
            )
            analysis = QueryAnalysis(
                raw_query=normalized,
                language=language,
                pipeline_failed=True,
            )
            analysis.search_terms = build_search_terms(analysis, self._config)
            analysis.lexical_query = (
                " ".join(analysis.search_terms) or normalized
            )
            analysis.chunk_embedding_text = analysis.lexical_query
            return analysis

        return analyze_query_document(
            processed,
            normalized,
            language=language,
            config=self._config,
        )

    async def embed_analysis(
        self,
        analysis: QueryAnalysis,
    ) -> list[float]:
        """Generate the dense query embedding for an analysis.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(QueryAnalyzerTask.embed_analysis)
            True
        """
        zero = [0.0] * self._embedding_dim
        chunk_text = analysis.chunk_embedding_text or analysis.raw_query
        if self._config.use_chunk_embedding and chunk_text.strip():
            return await self._llm.embed(chunk_text)
        return zero

    def build_payload(
        self,
        analysis: QueryAnalysis,
        *,
        q_dense: list[float],
        hits: int | None = None,
    ) -> dict[str, Any]:
        """Build the Vespa HTTP payload from analysis and embeddings.

        Example:
            >>> class _LLM:
            ...     async def embed(self, text):
            ...         return [0.0] * 384
            >>> task = QueryAnalyzerTask(None, _LLM(), RagSearchConfig())  # doctest: +SKIP
        """
        return build_vespa_search_payload(
            analysis,
            self._config,
            q_dense=q_dense,
            hits=hits or self._config.hits,
            timeout_seconds=self._timeout_seconds,
            embedding_dim=self._embedding_dim,
            user_space=self._user_space,
        )

    async def process(
        self,
        raw_query: str,
        *,
        language: str | None = None,
        hits: int | None = None,
    ) -> dict[str, Any]:
        """Analyze a query and return a ready-to-send Vespa search payload.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(QueryAnalyzerTask.process)
            True
        """
        analysis = self.analyze_sync(raw_query, language=language)
        q_dense = await self.embed_analysis(analysis)
        payload = self.build_payload(
            analysis,
            q_dense=q_dense,
            hits=hits,
        )
        ThotLogger.info(
            "QueryAnalyzerTask "
            + f"terms={len(analysis.search_terms)} "
            + f"ner={len(analysis.ner_entities)} "
            + f"svo={len(analysis.svo_triples)} "
            + f"yql={payload.get('yql', '')[:240]}"
        )
        return {
            "payload": payload,
            "analysis": {
                "raw_query": analysis.raw_query,
                "language": analysis.language,
                "search_terms": analysis.search_terms,
                "lexical_query": analysis.lexical_query,
                "chunk_embedding_text": analysis.chunk_embedding_text,
                "ner_entities": [
                    {"text": entity.text, "label": entity.label}
                    for entity in analysis.ner_entities
                ],
                "svo_triples": [
                    {
                        "subject": triple.subject,
                        "verb": triple.verb,
                        "object": triple.object,
                    }
                    for triple in analysis.svo_triples
                ],
                "keywords": analysis.keywords,
                "pipeline_failed": analysis.pipeline_failed,
                "ranking_weights": {
                    "chunk_embedding": self._config.weight_chunk_embedding,
                    "text_raw_bm25": self._config.weight_text_raw_bm25,
                },
            },
        }
