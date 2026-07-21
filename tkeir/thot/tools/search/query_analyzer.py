"""Analyze user queries and build structured Vespa hybrid search payloads."""

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
    build_multi_field_contains_or_clause,
    build_text_raw_contains_or_clause,
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
    question_embedding_text: str = ""
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


def build_question_embedding_text(analysis: QueryAnalysis) -> str:
    """Build the implicit question string for ``q_question_emb``.

    Example:
        >>> analysis = QueryAnalysis(
        ...     raw_query="What did Microsoft acquire?",
        ...     language="en",
        ...     svo_triples=[SvoTriple("Microsoft", "acquire", "")],
        ... )
        >>> "Microsoft" in build_question_embedding_text(analysis)
        True
    """
    if analysis.svo_triples:
        parts: list[str] = []
        for triple in analysis.svo_triples:
            parts.extend(
                piece
                for piece in (triple.subject, triple.verb, triple.object)
                if piece
            )
        if parts:
            return " ".join(dict.fromkeys(parts))
    if analysis.ner_entities:
        return " ".join(entity.text for entity in analysis.ner_entities)
    return analysis.lexical_query or analysis.raw_query


def build_chunk_embedding_text(analysis: QueryAnalysis) -> str:
    """Build the query string for ``q_chunk_emb``.

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
        One of ``hybrid_semantic``, ``hybrid_lexical``, ``hybrid_2_level``.

    Example:
        >>> select_ranking_profile(QueryAnalysis(
        ...     raw_query="x", language="en",
        ...     ner_entities=[NerEntity("Microsoft", "ORG")],
        ...     search_terms=["Microsoft"],
        ... ))
        'hybrid_semantic'
    """
    terms = analysis.search_terms or []
    ner_count = len(analysis.ner_entities)
    lemma_count = len(analysis.lemmas)
    raw_tokens = max(
        1, len([part for part in analysis.raw_query.split() if part])
    )
    entity_ratio = ner_count / max(1, len(terms))
    lemma_ratio = lemma_count / raw_tokens
    # Sparse lexical anchors → rely on dense similarity (paraphrase/stance).
    if len(terms) <= 2 or lemma_ratio < 0.35:
        return "hybrid_semantic"
    # Entity-anchored queries → lexical hybrid.
    if entity_ratio >= 0.4 and ner_count >= 1:
        return "hybrid_lexical"
    # Structured SVO without strong entity anchors → balanced.
    if analysis.svo_triples and ner_count == 0:
        return "hybrid_semantic"
    return "hybrid_2_level"


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
        >>> yql = build_hybrid_yql(analysis, RagSearchConfig(use_chunk_embedding=False, use_question_embedding=False), hits=5)
        >>> "Microsoft" in yql
        True
    """
    yql_parts: list[str] = []
    if config.use_chunk_embedding:
        yql_parts.append(
            f'([{{"targetNumHits": {hits}}}]nearestNeighbor(chunk_embedding, q_chunk_emb))'
        )
    if config.use_question_embedding:
        yql_parts.append(
            f'([{{"targetNumHits": {hits}}}]nearestNeighbor(questions_embeddings, q_question_emb))'
        )

    bm25_fields: list[str] = []
    if config.use_text_raw:
        bm25_fields.append("text_raw")
    if config.use_parent_content:
        bm25_fields.append("parent_content")
    if config.use_parent_title:
        bm25_fields.append("parent_title")

    if bm25_fields and analysis.search_terms:
        text_clause = build_multi_field_contains_or_clause(
            analysis.search_terms,
            fields=tuple(bm25_fields),
        )
        if text_clause:
            yql_parts.append(text_clause)

    if not yql_parts:
        fallback = build_text_raw_contains_or_clause(analysis.raw_query)
        if fallback:
            yql_parts.append(fallback)
        else:
            yql_parts.append("true")

    return "select * from chunk where " + " or ".join(yql_parts)


def build_vespa_search_payload(
    analysis: QueryAnalysis,
    config: RagSearchConfig,
    *,
    q_chunk_emb: list[float],
    q_question_emb: list[float],
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
        ...     RagSearchConfig(use_question_embedding=False),
        ...     q_chunk_emb=[0.0] * 384,
        ...     q_question_emb=[0.0] * 384,
        ...     hits=10,
        ...     timeout_seconds=30.0,
        ...     embedding_dim=384,
        ...     user_space="demo",
        ... )
        >>> payload["ranking.profile"]
        'hybrid_semantic'
        >>> payload["streaming.groupname"]
        'demo'
    """
    profile = (config.ranking_profile or "auto").strip()
    if profile == "auto":
        profile = select_ranking_profile(analysis)
    payload: dict[str, Any] = {
        "yql": build_hybrid_yql(analysis, config, hits=hits),
        "hits": hits,
        "timeout": f"{int(timeout_seconds)}s",
        "ranking.profile": profile,
    }
    from thot.tools.search.vespa_client import normalize_user_space

    payload["streaming.groupname"] = normalize_user_space(user_space)
    if config.use_chunk_embedding:
        payload["input.query(q_chunk_emb)"] = build_chunk_tensor(
            q_chunk_emb,
            embedding_dim=embedding_dim,
        )
    if config.use_question_embedding:
        payload["input.query(q_question_emb)"] = build_chunk_tensor(
            q_question_emb,
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


def _append_unique_analysis_terms(
    parts: list[str],
    existing: str,
    analysis: dict[str, Any],
) -> None:
    """Append NER, SVO, and search terms not already present in ``existing``."""
    for entity in analysis.get("ner_entities") or []:
        text = str(entity.get("text", "")).strip()
        if text and text.lower() not in existing:
            parts.append(text)
    for triple in analysis.get("svo_triples") or []:
        for key in ("subject", "verb", "object"):
            text = str(triple.get(key, "")).strip()
            if text and text.lower() not in existing:
                parts.append(text)
    for term in analysis.get("search_terms") or []:
        text = str(term).strip()
        if text and text.lower() not in existing:
            parts.append(text)


def build_focus_query_text(
    *,
    raw_query: str,
    analysis: dict[str, Any] | None = None,
) -> str:
    """Build a query string for focus-passage ranking near the user request.

    Example:
        >>> build_focus_query_text(
        ...     raw_query="Who interpret the album Abbey Road",
        ...     analysis={
        ...         "ner_entities": [{"text": "Abbey Road", "label": "work"}],
        ...         "morphosyntax": [{"text": "Who", "pos": "PRON"}],
        ...     },
        ... )
        'Who interpret the album Abbey Road'
    """
    normalized = (raw_query or "").strip()
    if normalized and is_entity_report_query(normalized, analysis):
        focal = _focal_entity_from_query(normalized, analysis)
        if focal:
            return focal
    parts: list[str] = []
    if normalized:
        parts.append(normalized)
    if analysis:
        _append_unique_analysis_terms(parts, normalized.lower(), analysis)
    if parts:
        return " ".join(dict.fromkeys(parts))
    return normalized


def _entity_after_adp(morphosyntax: list[dict[str, Any]]) -> str | None:
    """Return the span after a preposition token (report-about-X patterns).

    Example:
        >>> morph = [
        ...     {"text": "about", "pos": "ADP"},
        ...     {"text": "Claudio", "pos": "PROPN"},
        ...     {"text": "Miranda", "pos": "PROPN"},
        ... ]
        >>> _entity_after_adp(morph)
        'Claudio Miranda'
    """
    for index, token in enumerate(morphosyntax):
        if str(token.get("pos", "")).upper() != "ADP":
            continue
        tail = [
            str(item.get("text", "")).strip()
            for item in morphosyntax[index + 1 :]
            if str(item.get("text", "")).strip()
        ]
        if not tail:
            continue
        candidate = " ".join(tail).strip(" ?.!")
        if candidate and len(candidate.split()) <= 8:
            return candidate
    return None


def _query_starts_with_interrogative(analysis: dict[str, Any] | None) -> bool:
    """Return whether morphosyntax marks the query as a direct question.

    Example:
        >>> _query_starts_with_interrogative(
        ...     {"morphosyntax": [{"text": "Who", "pos": "PRON"}]}
        ... )
        True
    """
    morph = (analysis or {}).get("morphosyntax") or []
    if not morph:
        return False
    first_pos = str(morph[0].get("pos", "")).upper()
    return first_pos in {"PRON", "ADV", "DET"}


def _focal_entity_from_query(
    query_text: str,
    analysis: dict[str, Any] | None = None,
) -> str | None:
    """Extract the main entity for report-style questions when possible.

    Example:
        >>> _focal_entity_from_query(
        ...     "Generate a report about Claudio Miranda",
        ...     {"ner_entities": [{"text": "Claudio Miranda", "label": "person"}]},
        ... )
        'Claudio Miranda'
    """
    query = (query_text or "").strip()
    if not query:
        return None

    if analysis:
        for entity in analysis.get("ner_entities") or []:
            text = str(entity.get("text", "")).strip()
            if text and len(text.split()) <= 8:
                return text
        morph = analysis.get("morphosyntax") or []
        after_adp = _entity_after_adp(morph)
        if after_adp:
            return after_adp

    for match in re.finditer(r'"([^"]{2,80})"|\'([^\']{2,80})\'', query):
        candidate = (match.group(1) or match.group(2) or "").strip()
        if candidate:
            return candidate
    return None


def detect_generation_intent(
    query_text: str,
    analysis: dict[str, Any] | None = None,
) -> str:
    """Classify the user request for prompt-specific generation guidance.

    Uses NLP analysis when available; no fixed natural-language keyword lists.

    Example:
        >>> detect_generation_intent(
        ...     "Generate a report about Claudio Miranda",
        ...     {"ner_entities": [{"text": "Claudio Miranda", "label": "person"}]},
        ... )
        'entity_report'
        >>> detect_generation_intent(
        ...     "Who won the Oscar?",
        ...     {"morphosyntax": [{"text": "Who", "pos": "PRON"}]},
        ... )
        'question_answer'
    """
    if _query_starts_with_interrogative(analysis):
        return "question_answer"

    focal = _focal_entity_from_query(query_text, analysis)
    if focal and analysis:
        morph = analysis.get("morphosyntax") or []
        if morph:
            if _entity_after_adp(morph):
                return "entity_report"
            lemmas = (
                analysis.get("lemmas") or analysis.get("search_terms") or []
            )
            if analysis.get("ner_entities") and len(lemmas) >= 2:
                return "entity_report"
        elif analysis.get("ner_entities"):
            return "entity_report"

    return "general"


def is_entity_report_query(
    query_text: str,
    analysis: dict[str, Any] | None = None,
) -> bool:
    """Return whether the query asks for a structured report about an entity.

    Example:
        >>> is_entity_report_query(
        ...     "Generate a report about Claudio Miranda",
        ...     {"ner_entities": [{"text": "Claudio Miranda", "label": "person"}]},
        ... )
        True
    """
    return detect_generation_intent(query_text, analysis) == "entity_report"


def format_generation_guidance(
    query_text: str,
    analysis: dict[str, Any] | None = None,
    *,
    language: str = "en",
) -> str:
    """Return intent-specific instructions appended to the LLM user prompt.

    Example:
        >>> text = format_generation_guidance(
        ...     "Generate a report about Claudio Miranda",
        ...     {"ner_entities": [{"text": "Claudio Miranda", "label": "person"}]},
        ... )
        >>> "entity report" in text.lower()
        True
        >>> "Claudio Miranda" in text
        True
    """
    intent = detect_generation_intent(query_text, analysis)
    focal = _focal_entity_from_query(query_text, analysis)
    lang = (language or "en").lower()

    if intent == "entity_report":
        subject = focal or (
            "la personne ou le sujet nommé dans la question"
            if lang == "fr"
            else "the person or topic named in the question"
        )
        if lang == "fr":
            return (
                "MODE DE GÉNÉRATION : rapport sur une entité\n"
                f"- Rédigez un rapport factuel sur **{subject}** en utilisant "
                "TOUS les faits pertinents des PASSAGES CLÉS, faits SVO et extraits.\n"
                "- SHORT_ANSWER : 2–4 phrases — identité, rôle principal, "
                "réalisation ou fait marquant.\n"
                "- DETAILED_REPORT : rapport markdown riche avec sections "
                "(## Aperçu, ## Parcours, ## Carrière, ## Distinctions, "
                "## Vie personnelle, ## Faits clés) selon le contexte.\n"
                "- Fusionnez les faits dispersés ; incluez dates, lieux, titres, "
                "films/projets, collaborateurs et prix.\n"
                "- Ignorez le bruit Wikipédia (Active entities, Topic, navigation).\n"
                f"- Ne répondez pas indisponible si un passage contient des faits sur {subject}."
            )
        return (
            "GENERATION MODE: entity report\n"
            f"- Write a factual report about **{subject}** using ALL relevant facts "
            "from KEY PASSAGES, SVO facts, and any supplementary excerpts below.\n"
            "- SHORT_ANSWER: 2–4 complete sentences — who/what they are, main role, "
            "and the most notable achievement or fact from the context.\n"
            "- DETAILED_REPORT: a rich markdown report (multiple paragraphs). "
            "Use these sections when the context supports them (skip empty ones):\n"
            "  ## Overview\n"
            "  ## Background\n"
            "  ## Career and notable work\n"
            "  ## Awards and recognition\n"
            "  ## Personal life\n"
            "  ## Key facts\n"
            "- Merge facts scattered across passages into one coherent narrative.\n"
            "- Include concrete details: dates, places, job titles, films/projects, "
            "collaborators, awards, and organizations when present in the context.\n"
            "- Ignore Wikipedia or index noise (Active entities, Topic, edit links, "
            "cookie banners, navigation menus).\n"
            f"- Do NOT reply unavailable if any passage contains facts about {subject}."
        )

    if intent == "question_answer":
        if lang == "fr":
            return (
                "MODE DE GÉNÉRATION : réponse directe\n"
                "- SHORT_ANSWER : réponse directe en 1–3 phrases.\n"
                "- DETAILED_REPORT : explication appuyée par les passages "
                "(noms, dates, événements).\n"
                "- Privilégiez les PASSAGES CLÉS aux lignes SVO isolées."
            )
        return (
            "GENERATION MODE: direct question answering\n"
            "- SHORT_ANSWER: answer the question directly in 1–3 sentences.\n"
            "- DETAILED_REPORT: explain the answer with supporting facts from the "
            "passages; cite names, dates, and events explicitly.\n"
            "- Prefer KEY PASSAGES over isolated SVO lines when they conflict."
        )

    if lang == "fr":
        return (
            "MODE DE GÉNÉRATION : synthèse générale\n"
            "- SHORT_ANSWER : réponse concise ancrée dans les passages.\n"
            "- DETAILED_REPORT : synthèse markdown structurée.\n"
            "- Phrases complètes avec noms, dates et rôles."
        )
    return (
        "GENERATION MODE: general synthesis\n"
        "- SHORT_ANSWER: concise factual answer grounded in the passages.\n"
        "- DETAILED_REPORT: structured markdown synthesis of all relevant facts.\n"
        "- Use complete sentences and include specific names, dates, and roles."
    )


def build_svo_question_restatement(
    svo_triples: list[dict[str, Any]],
) -> str:
    """Restate the user question from extracted SVO triples.

    Example:
        >>> build_svo_question_restatement(
        ...     [{"subject": "Microsoft", "verb": "acquire", "object": "GitHub"}]
        ... )
        'Microsoft acquire GitHub'
    """
    readings: list[str] = []
    for triple in svo_triples:
        subject = str(triple.get("subject", "")).strip()
        verb = str(triple.get("verb", "")).strip()
        obj = str(triple.get("object", "")).strip()
        if subject and verb and obj:
            readings.append(f"{subject} {verb} {obj}")
        elif subject and verb:
            readings.append(f"{subject} {verb} …")
        elif subject:
            readings.append(subject)
    return "; ".join(readings)


def _format_svo_analysis_section(
    svo_triples: list[dict[str, Any]],
) -> list[str]:
    """Format the SVO section for prompt query analysis."""
    lines = ["PRIMARY — question structure (SVO):"]
    for triple in svo_triples:
        subject = str(triple.get("subject", "")).strip()
        verb = str(triple.get("verb", "")).strip()
        obj = str(triple.get("object", "")).strip()
        if subject or verb or obj:
            lines.append(f"  - {subject} | {verb} | {obj}")
    restatement = build_svo_question_restatement(svo_triples)
    if restatement:
        lines.append(f"- SVO-aligned reading: {restatement}")
    lines.extend(
        [
            "Interpret the user question through this SVO structure first; "
            "prefer facts and passages that match these subject-verb-object relations.",
            "",
        ]
    )
    return lines


def _format_ner_analysis_section(
    ner_entities: list[dict[str, Any]],
) -> list[str]:
    """Format the named-entity section for prompt query analysis."""
    lines = ["- Named entities:"]
    for entity in ner_entities:
        text = str(entity.get("text", "")).strip()
        label = str(entity.get("label", "entity")).strip()
        if text:
            lines.append(f"  - {text} ({label})")
    return lines


def format_query_analysis_for_prompt(
    *,
    raw_query: str,
    lexical_query: str,
    analysis: dict[str, Any] | None = None,
) -> str:
    """Format analyzed query metadata for inclusion in the RAG user prompt.

    SVO triples are placed first so generation stays aligned with the
    subject-verb-object structure of the request.

    Example:
        >>> text = format_query_analysis_for_prompt(
        ...     raw_query="What did Microsoft acquire?",
        ...     lexical_query="Microsoft acquire",
        ...     analysis={
        ...         "svo_triples": [{"subject": "Microsoft", "verb": "acquire", "object": ""}],
        ...         "search_terms": ["Microsoft", "acquire"],
        ...     },
        ... )
        >>> text.startswith("PRIMARY")
        True
    """
    lines: list[str] = []
    svo_triples = (analysis or {}).get("svo_triples") or []

    if svo_triples:
        lines.extend(_format_svo_analysis_section(svo_triples))

    lines.extend(
        [
            f"- Raw question: {raw_query.strip()}",
            f"- Lexical search query: {(lexical_query or raw_query).strip()}",
        ]
    )
    if not analysis:
        return "\n".join(lines)

    search_terms = analysis.get("search_terms") or []
    if search_terms:
        lines.append(
            f"- Search terms: {', '.join(str(term) for term in search_terms)}"
        )

    ner_entities = analysis.get("ner_entities") or []
    if ner_entities:
        lines.extend(_format_ner_analysis_section(ner_entities))

    keywords = analysis.get("keywords") or []
    if keywords:
        lines.append(
            f"- Keywords: {', '.join(str(keyword) for keyword in keywords)}"
        )

    return "\n".join(lines)


_VESPA_EMBEDDING_KEYS = (
    "input.query(q_chunk_emb)",
    "input.query(q_question_emb)",
)


def format_vespa_query_json(payload: dict[str, Any]) -> str:
    """Serialize a Vespa search payload as pretty-printed JSON.

    Embedding vectors are omitted from the API/report payload to keep
    responses compact.

    Example:
        >>> rendered = format_vespa_query_json({
        ...     "yql": "select * from chunk where true",
        ...     "input.query(q_chunk_emb)": [0.1, 0.2],
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
    analysis.question_embedding_text = build_question_embedding_text(analysis)
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
            analysis.question_embedding_text = normalized
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
    ) -> tuple[list[float], list[float]]:
        """Generate chunk and question embeddings for an analysis.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(QueryAnalyzerTask.embed_analysis)
            True
        """
        zero = [0.0] * self._embedding_dim
        chunk_text = analysis.chunk_embedding_text or analysis.raw_query
        question_text = analysis.question_embedding_text or analysis.raw_query

        q_chunk_emb = zero
        q_question_emb = zero

        if self._config.use_chunk_embedding and chunk_text.strip():
            q_chunk_emb = await self._llm.embed(chunk_text)
        if self._config.use_question_embedding and question_text.strip():
            q_question_emb = await self._llm.embed(question_text)
        elif (
            self._config.use_question_embedding
            and self._config.use_chunk_embedding
        ):
            q_question_emb = q_chunk_emb

        return q_chunk_emb, q_question_emb

    def build_payload(
        self,
        analysis: QueryAnalysis,
        *,
        q_chunk_emb: list[float],
        q_question_emb: list[float],
        hits: int | None = None,
    ) -> dict[str, Any]:
        """Build the Vespa HTTP payload from analysis and embeddings.

        Example:
            >>> class _LLM:
            ...     async def embed(self, text):
            ...         return [0.0] * 384
            >>> task = QueryAnalyzerTask(None, _LLM(), RagSearchConfig(use_question_embedding=False))  # doctest: +SKIP
        """
        return build_vespa_search_payload(
            analysis,
            self._config,
            q_chunk_emb=q_chunk_emb,
            q_question_emb=q_question_emb,
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
        q_chunk_emb, q_question_emb = await self.embed_analysis(analysis)
        payload = self.build_payload(
            analysis,
            q_chunk_emb=q_chunk_emb,
            q_question_emb=q_question_emb,
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
                "question_embedding_text": analysis.question_embedding_text,
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
                    "question_embedding": (
                        self._config.weight_question_embedding
                    ),
                    "text_raw_bm25": self._config.weight_text_raw_bm25,
                    "parent_content_bm25": (
                        self._config.weight_parent_content_bm25
                    ),
                    "parent_title_bm25": self._config.weight_parent_title_bm25,
                },
            },
        }
