"""Title: Generation prompt helpers.

Build LLM prompt guidance from NLP query analysis output.
Not part of query analysis / Vespa retrieval.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re
from typing import Any


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

