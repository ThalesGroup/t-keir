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


def _ner_entity_text(entity: Any) -> str:
    """Normalize a NER entry (dict or bare string) to display text."""
    if isinstance(entity, dict):
        return str(entity.get("text", "")).strip()
    return str(entity or "").strip()


def _ner_entity_label(entity: Any) -> str:
    """Normalize a NER entry (dict or bare string) to a label."""
    if isinstance(entity, dict):
        return str(entity.get("label", "entity")).strip() or "entity"
    return "entity"


def _append_unique_analysis_terms(
    parts: list[str],
    existing: str,
    analysis: dict[str, Any],
) -> None:
    """Append NER, SVO, and search terms not already present in ``existing``."""
    for entity in analysis.get("ner_entities") or []:
        text = _ner_entity_text(entity)
        if text and text.lower() not in existing:
            parts.append(text)
    for triple in analysis.get("svo_triples") or []:
        if not isinstance(triple, dict):
            continue
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
    first_text = str(morph[0].get("text", "")).strip().lower()
    if first_pos in {"PRON", "ADV", "DET", "AUX", "MD"}:
        return True
    return first_text in {
        "who",
        "whom",
        "whose",
        "what",
        "when",
        "where",
        "why",
        "how",
        "which",
        "is",
        "are",
        "was",
        "were",
        "do",
        "does",
        "did",
        "can",
        "could",
        "will",
        "would",
        "should",
        "has",
        "have",
        "had",
        "may",
        "might",
    }


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
            text = _ner_entity_text(entity)
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
    # Direct questions always win over entity-report heuristics.
    if _query_starts_with_interrogative(analysis):
        return "question_answer"
    query = (query_text or "").strip()
    if query.endswith("?"):
        return "question_answer"
    first = query.split(None, 1)[0].lower().strip("¿¡") if query else ""
    if first in {
        "who",
        "what",
        "when",
        "where",
        "why",
        "how",
        "which",
        "is",
        "are",
        "was",
        "were",
        "do",
        "does",
        "did",
        "can",
        "could",
        "will",
        "would",
        "should",
        "has",
        "have",
        "had",
    }:
        return "question_answer"

    focal = _focal_entity_from_query(query_text, analysis)
    if focal and analysis:
        morph = analysis.get("morphosyntax") or []
        lemmas = analysis.get("lemmas") or analysis.get("search_terms") or []
        lemma_l = {str(item).lower() for item in lemmas}
        report_lemmas = {
            "generate",
            "report",
            "summarize",
            "summary",
            "profile",
            "biography",
            "write",
        }
        if morph and _entity_after_adp(morph) and lemma_l & report_lemmas:
            return "entity_report"
        if analysis.get("ner_entities") and lemma_l & report_lemmas:
            return "entity_report"
        if any(
            token in query.lower()
            for token in (
                "report about",
                "profile of",
                "biography of",
                "summary of",
            )
        ):
            return "entity_report"

    return "general"


def detect_question_type(
    query_text: str,
    analysis: dict[str, Any] | None = None,
) -> str:
    """Fine-grained QA type for sharp SHORT_ANSWER shaping.

    Returns one of: ``yes_no``, ``definition``, ``who``, ``what``, ``when``,
    ``where``, ``why``, ``how``, ``which``, ``list``, ``comparison``,
    ``factoid``, ``inference``, ``entity_report``, ``other``.

    Interrogative / yes-no patterns are classified **before** entity_report.

    Example:
        >>> detect_question_type(
        ...     "Who founded Acme?",
        ...     {"morphosyntax": [{"text": "Who", "pos": "PRON"}]},
        ... )
        'who'
        >>> detect_question_type(
        ...     "Does the article claim X?",
        ...     {"morphosyntax": [{"text": "Does", "pos": "AUX"}],
        ...      "ner_entities": [{"text": "X", "label": "MISC"}]},
        ... )
        'yes_no'
    """
    query = (query_text or "").strip()
    lower = query.lower()
    morph = (analysis or {}).get("morphosyntax") or []
    first_text = ""
    first_pos = ""
    if morph:
        first_text = str(morph[0].get("text") or "").strip().lower()
        first_pos = str(morph[0].get("pos") or "").strip().upper()
    if not first_text and query:
        first_text = query.split(None, 1)[0].lower().strip("¿¡")

    yes_no_openers = {
        "is",
        "are",
        "was",
        "were",
        "do",
        "does",
        "did",
        "can",
        "could",
        "will",
        "would",
        "should",
        "has",
        "have",
        "had",
        "may",
        "might",
    }
    if first_text in yes_no_openers or (
        first_pos in {"AUX", "MD"}
        and first_text
        not in {"who", "what", "when", "where", "why", "how", "which"}
    ):
        return "yes_no"

    # Inverted / mid-clause yes-no (e.g. "Between A and B, was there …?")
    if re.search(
        r"\b(is|are|was|were|do|does|did|can|could|will|would|should|"
        r"has|have|had)\s+(there|it|this|that|he|she|they)\b",
        lower,
    ) or re.search(
        r"\b(is|are|was|were)\s+\w+\s+(true|false|correct|consistent|"
        r"inconsistent|accurate)\b",
        lower,
    ):
        return "yes_no"

    wh_map = {
        "who": "who",
        "whom": "who",
        "whose": "who",
        "what": "what",
        "when": "when",
        "where": "where",
        "why": "why",
        "how": "how",
        "which": "which",
    }
    if first_text in wh_map:
        qtype = wh_map[first_text]
        if qtype == "what" and (
            lower.startswith("what is ")
            or lower.startswith("what are ")
            or lower.startswith("what does ")
            or " mean" in lower
            or "definition" in lower
        ):
            return "definition"
        if qtype in {"what", "which", "who"} and any(
            token in lower
            for token in (
                " which of ",
                " list ",
                " name all ",
                " name the ",
                " what are the ",
                " which are ",
            )
        ):
            return "list"
        return qtype

    if any(
        token in lower
        for token in (
            "compare ",
            " vs ",
            " versus ",
            "difference between",
            "differ from",
            "in contrast",
        )
    ):
        return "comparison"

    if any(
        token in lower
        for token in ("list ", "enumerate ", "name all ", "all of the ")
    ):
        return "list"

    ner = (analysis or {}).get("ner_entities") or []
    if len(ner) >= 2 and (
        " and " in lower
        or "," in query
        or " according to " in lower
        or " reported by " in lower
        or " in contrast " in lower
        or " both " in lower
    ):
        return "inference"
    if query.count("?") >= 1 and len(query.split()) >= 25:
        return "inference"

    if detect_generation_intent(query_text, analysis) == "entity_report":
        return "entity_report"

    if _query_starts_with_interrogative(analysis) or query.endswith("?"):
        return "factoid"
    return "other"


def question_type_short_answer_spec(
    question_type: str, *, language: str = "en"
) -> str:
    """Return SHORT_ANSWER shape instructions for a question type."""
    lang = (language or "en").lower()
    specs_en = {
        "yes_no": (
            "SHORT_ANSWER must be Yes or No (optionally one short justifying clause). "
            "Do not hedge with both."
        ),
        "definition": (
            "SHORT_ANSWER must define the term in 1–2 precise sentences "
            "(genus + distinguishing properties)."
        ),
        "who": (
            "SHORT_ANSWER must name the person/organization (plus a brief role if needed)."
        ),
        "what": "SHORT_ANSWER must name the thing/event/result directly.",
        "when": (
            "SHORT_ANSWER must give the date, year, or time span explicitly."
        ),
        "where": "SHORT_ANSWER must give the place/location explicitly.",
        "why": "SHORT_ANSWER must state the cause/reason in 1–2 sentences.",
        "how": (
            "SHORT_ANSWER must state the manner/mechanism in 1–3 sentences."
        ),
        "which": (
            "SHORT_ANSWER must select the matching option(s) from the evidence."
        ),
        "list": (
            "SHORT_ANSWER must be a compact enumeration (comma-separated or short bullets)."
        ),
        "comparison": (
            "SHORT_ANSWER must contrast the compared entities on the asked dimension."
        ),
        "factoid": (
            "SHORT_ANSWER must be a concise factual span answering the question."
        ),
        "inference": (
            "SHORT_ANSWER must combine evidence across passages into one grounded conclusion."
        ),
        "entity_report": (
            "SHORT_ANSWER must summarize the entity in 2–4 factual sentences."
        ),
        "other": (
            "SHORT_ANSWER must answer the question directly and concisely."
        ),
    }
    specs_fr = {
        "yes_no": (
            "SHORT_ANSWER doit être Oui ou Non (clause justificative courte optionnelle)."
        ),
        "definition": (
            "SHORT_ANSWER doit définir le terme en 1–2 phrases précises."
        ),
        "who": "SHORT_ANSWER doit nommer la personne/organisation.",
        "what": "SHORT_ANSWER doit nommer directement la chose/l'événement.",
        "when": "SHORT_ANSWER doit donner la date, l'année ou la période.",
        "where": "SHORT_ANSWER doit donner le lieu explicitement.",
        "why": "SHORT_ANSWER doit énoncer la cause en 1–2 phrases.",
        "how": "SHORT_ANSWER doit décrire le mécanisme en 1–3 phrases.",
        "which": (
            "SHORT_ANSWER doit sélectionner la/les option(s) pertinentes."
        ),
        "list": "SHORT_ANSWER doit être une énumération compacte.",
        "comparison": (
            "SHORT_ANSWER doit comparer les entités sur le critère demandé."
        ),
        "factoid": "SHORT_ANSWER doit être une réponse factuelle concise.",
        "inference": (
            "SHORT_ANSWER doit combiner les preuves en une conclusion fondée."
        ),
        "entity_report": "SHORT_ANSWER doit résumer l'entité en 2–4 phrases.",
        "other": "SHORT_ANSWER doit répondre directement et concisément.",
    }
    table = specs_fr if lang == "fr" else specs_en
    return table.get(question_type) or table["other"]


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
    qtype = detect_question_type(query_text, analysis)
    short_spec = question_type_short_answer_spec(qtype, language=language)
    focal = _focal_entity_from_query(query_text, analysis)
    lang = (language or "en").lower()
    type_header = (
        f"QUESTION TYPE: {qtype}\n- {short_spec}"
        if lang != "fr"
        else f"TYPE DE QUESTION : {qtype}\n- {short_spec}"
    )

    if intent == "entity_report" or qtype == "entity_report":
        subject = focal or (
            "la personne ou le sujet nommé dans la question"
            if lang == "fr"
            else "the person or topic named in the question"
        )
        if lang == "fr":
            return (
                f"{type_header}\n"
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
            f"{type_header}\n"
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

    if intent == "question_answer" or qtype not in {"other", "entity_report"}:
        if lang == "fr":
            return (
                f"{type_header}\n"
                "MODE DE GÉNÉRATION : réponse directe\n"
                "- Alignez la réponse sur la structure SVO de la question.\n"
                "- SHORT_ANSWER et DETAILED_REPORT doivent paraphraser uniquement "
                "les PASSAGES CLÉS.\n"
                "- N'ajoutez aucune connaissance générale absente des passages.\n"
                "- DETAILED_REPORT : explication appuyée par les passages "
                "(noms, dates, événements).\n"
                "- Privilégiez les PASSAGES CLÉS aux lignes SVO isolées."
            )
        return (
            f"{type_header}\n"
            "GENERATION MODE: direct question answering\n"
            "- Align the answer with the question's SVO structure "
            "(subject / verb / object from SEARCH QUERY ANALYSIS).\n"
            "- SHORT_ANSWER and DETAILED_REPORT must paraphrase KEY PASSAGES only.\n"
            "- Never add world-knowledge or historical facts absent from the passages.\n"
            "- DETAILED_REPORT: explain the answer with supporting facts from the "
            "passages; cite names, dates, and events explicitly.\n"
            "- Prefer KEY PASSAGES over isolated SVO lines when they conflict."
        )

    if lang == "fr":
        return (
            f"{type_header}\n"
            "MODE DE GÉNÉRATION : synthèse générale\n"
            "- SHORT_ANSWER : réponse concise ancrée dans les passages.\n"
            "- DETAILED_REPORT : synthèse markdown structurée.\n"
            "- Phrases complètes avec noms, dates et rôles."
        )
    return (
        f"{type_header}\n"
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
    ner_entities: list[Any],
) -> list[str]:
    """Format the named-entity section for prompt query analysis."""
    lines = ["- Named entities:"]
    for entity in ner_entities:
        text = _ner_entity_text(entity)
        label = _ner_entity_label(entity)
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
    if analysis:
        qtype = detect_question_type(raw_query, analysis)
        lines.append(f"- Question type: {qtype}")
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
