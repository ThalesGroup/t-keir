# -*- coding: utf-8 -*-
"""RAG report assembly: structured answers, markdown export, highlight labels."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from thot.tools.search.app import FusedOntology, RetrievedChunk

_SHORT_ANSWER_MARKER = "SHORT_ANSWER:"
_DETAILED_REPORT_MARKER = "DETAILED_REPORT:"


def _format_document_name(parent_doc_id: str) -> str:
    """Return a short display name from a parent document URI.

    Example:
        >>> _format_document_name("file://tests/input/doc.pdf")
        'doc.pdf'
    """
    without_scheme = parent_doc_id.replace("file://", "")
    return without_scheme.split("/")[-1] or parent_doc_id


def parse_structured_generation(
    raw_text: str,
    *,
    unavailable_answer: str,
) -> tuple[str, str]:
    """Split an LLM response into a short answer and detailed report body.

    Args:
        raw_text: Raw model output expected to contain ``SHORT_ANSWER`` and
            ``DETAILED_REPORT`` sections.
        unavailable_answer: Fallback short answer when parsing fails.

    Returns:
        Tuple of ``(short_answer, detailed_report_markdown)``.

    Example:
        >>> text = "SHORT_ANSWER:\\nYes.\\n\\nDETAILED_REPORT:\\n## Detailed Analysis\\nMore."
        >>> short, detail = parse_structured_generation(text, unavailable_answer="N/A")
        >>> short
        'Yes.'
        >>> "## Detailed Analysis" in detail
        True
    """
    cleaned = raw_text.strip()
    if not cleaned:
        return unavailable_answer, ""

    upper = cleaned.upper()
    short_start = upper.find(_SHORT_ANSWER_MARKER)
    report_start = upper.find(_DETAILED_REPORT_MARKER)

    if short_start >= 0 and report_start > short_start:
        short_answer = cleaned[
            short_start + len(_SHORT_ANSWER_MARKER) : report_start
        ].strip()
        detailed_report = cleaned[
            report_start + len(_DETAILED_REPORT_MARKER) :
        ].strip()
        if short_answer:
            return short_answer, detailed_report

    if report_start >= 0:
        detailed_report = cleaned[
            report_start + len(_DETAILED_REPORT_MARKER) :
        ].strip()
        short_answer = cleaned[:report_start].strip() or unavailable_answer
        return short_answer, detailed_report

    paragraphs = [
        part.strip() for part in cleaned.split("\n\n") if part.strip()
    ]
    if not paragraphs:
        return unavailable_answer, ""
    if len(paragraphs) == 1:
        return paragraphs[0], ""
    return paragraphs[0], "\n\n".join(paragraphs[1:])


def extract_highlight_labels(
    ontology: dict[str, Any] | FusedOntology,
    *,
    max_entities: int = 20,
    max_keywords: int = 15,
) -> tuple[list[str], list[str]]:
    """Return the most representative entity and keyword labels for highlighting.

    Example:
        >>> labels = extract_highlight_labels({
        ...     "entities": [{"label": "Acme", "type": "Company", "chunk_ids": ["c1", "c2"]}],
        ...     "keywords": [{"label": "launch", "chunk_ids": ["c1"]}],
        ... })
        >>> labels[0]
        ['Acme']
    """
    entities = (
        ontology.get("entities", [])
        if isinstance(ontology, dict)
        else ontology.entities
    )
    keywords = (
        ontology.get("keywords", [])
        if isinstance(ontology, dict)
        else ontology.keywords
    )

    ranked_entities = sorted(
        entities,
        key=lambda item: (
            -len(
                item.get("chunk_ids", [])
                if isinstance(item, dict)
                else item.chunk_ids
            ),
            str(
                item.get("label", "") if isinstance(item, dict) else item.label
            ).lower(),
        ),
    )
    ranked_keywords = sorted(
        keywords,
        key=lambda item: (
            -len(
                item.get("chunk_ids", [])
                if isinstance(item, dict)
                else item.chunk_ids
            ),
            str(
                item.get("label", "") if isinstance(item, dict) else item.label
            ).lower(),
        ),
    )

    entity_labels = [
        str(
            item.get("label", "") if isinstance(item, dict) else item.label
        ).strip()
        for item in ranked_entities[:max_entities]
        if str(
            item.get("label", "") if isinstance(item, dict) else item.label
        ).strip()
    ]
    keyword_labels = [
        str(
            item.get("label", "") if isinstance(item, dict) else item.label
        ).strip()
        for item in ranked_keywords[:max_keywords]
        if str(
            item.get("label", "") if isinstance(item, dict) else item.label
        ).strip()
    ]
    return entity_labels, keyword_labels


def _format_relevance(relevance: float | None) -> str:
    """Format a Vespa relevance score for markdown display.

    Example:
        >>> _format_relevance(0.8123)
        '81.2%'
        >>> _format_relevance(None)
        'n/a'
    """
    if relevance is None:
        return "n/a"
    return f"{relevance * 100:.1f}%"


def _ontology_section_markdown(
    ontology: dict[str, Any] | FusedOntology,
) -> str:
    """Build the ontology section of a downloadable RAG report.

    Example:
        >>> md = _ontology_section_markdown({"entities": [], "keywords": []})
        >>> "## Key Entities" in md
        True
    """
    entities = (
        ontology.get("entities", [])
        if isinstance(ontology, dict)
        else ontology.entities
    )
    keywords = (
        ontology.get("keywords", [])
        if isinstance(ontology, dict)
        else ontology.keywords
    )

    grouped: dict[str, list[str]] = defaultdict(list)
    for entity in entities:
        label = str(
            entity.get("label", "")
            if isinstance(entity, dict)
            else entity.label
        ).strip()
        entity_type = str(
            entity.get("type", "") if isinstance(entity, dict) else entity.type
        ).strip()
        if label:
            grouped[entity_type or "Entity"].append(label)

    lines = ["## Key Entities", ""]
    if grouped:
        for entity_type in sorted(grouped):
            unique_labels = sorted(set(grouped[entity_type]), key=str.lower)
            lines.append(f"- **{entity_type}:** {', '.join(unique_labels)}")
    else:
        lines.append("- No named entities linked to retrieved chunks.")

    lines.extend(["", "## Key Keywords", ""])
    keyword_labels = sorted(
        {
            str(
                item.get("label", "") if isinstance(item, dict) else item.label
            ).strip()
            for item in keywords
            if str(
                item.get("label", "") if isinstance(item, dict) else item.label
            ).strip()
        },
        key=str.lower,
    )
    if keyword_labels:
        lines.append("- " + ", ".join(keyword_labels))
    else:
        lines.append("- No keywords linked to retrieved chunks.")

    return "\n".join(lines)


def _sources_section_markdown(chunks: list[RetrievedChunk]) -> str:
    """Build the retrieved-sources section of a downloadable RAG report.

    Example:
        >>> _sources_section_markdown([])
        '## Retrieved Sources\\n\\nNo chunks retrieved.'
    """
    lines = ["## Retrieved Sources", ""]
    if not chunks:
        lines.append("No chunks retrieved.")
        return "\n".join(lines)

    by_document: dict[str, list[RetrievedChunk]] = defaultdict(list)
    for chunk in chunks:
        by_document[chunk.parent_doc_id].append(chunk)

    for parent_doc_id, doc_chunks in sorted(
        by_document.items(),
        key=lambda item: _format_document_name(item[0]).lower(),
    ):
        display_name = _format_document_name(parent_doc_id)
        lines.append(f"### Document: `{display_name}`")
        lines.append("")
        lines.append(f"- Source URI: `{parent_doc_id}`")
        lines.append("")

        for chunk in sorted(
            doc_chunks,
            key=lambda item: item.relevance or 0.0,
            reverse=True,
        ):
            lines.append(
                f"#### Chunk `{chunk.chunk_id}` "
                f"(relevance: {_format_relevance(chunk.relevance)})"
            )
            lines.append("")
            excerpt = re.sub(r"\s+", " ", chunk.text_raw).strip()
            if len(excerpt) > 1200:
                excerpt = f"{excerpt[:1200].rstrip()}…"
            lines.append(f"> {excerpt}")
            lines.append("")

    return "\n".join(lines)


def build_fallback_detailed_report(
    *,
    focus_passages: str,
    chunk_excerpts: str,
) -> str:
    """Build a deterministic detailed report when the LLM body is empty.

    Example:
        >>> report = build_fallback_detailed_report(
        ...     focus_passages="- [c1] Fact one.",
        ...     chunk_excerpts="---\\nChunk body\\n---",
        ... )
        >>> "## Detailed Analysis" in report
        True
    """
    lines = [
        "## Detailed Analysis",
        "",
        "The following passages from retrieved chunks are most relevant to the query.",
        "",
    ]
    if (
        focus_passages.strip()
        and focus_passages != "No focused passages identified."
    ):
        lines.extend(["### Focus Passages", "", focus_passages, ""])
    if chunk_excerpts.strip():
        lines.extend(
            [
                "### Supporting Excerpts",
                "",
                "```text",
                chunk_excerpts,
                "```",
                "",
            ]
        )
    return "\n".join(lines).strip()


def assemble_report_markdown(
    *,
    query: str,
    language: str,
    short_answer: str,
    detailed_report: str,
    chunks: list[RetrievedChunk],
    ontology: dict[str, Any] | FusedOntology,
    vespa_hits: int,
) -> str:
    """Assemble the downloadable markdown report for a RAG query.

    Example:
        >>> from thot.tools.search.app import RetrievedChunk
        >>> report = assemble_report_markdown(
        ...     query="Who is Alice?",
        ...     language="en",
        ...     short_answer="Alice works at Acme.",
        ...     detailed_report="## Detailed Analysis\\nAlice is mentioned.",
        ...     chunks=[RetrievedChunk(chunk_id="c1", text_raw="Alice works at Acme.", parent_doc_id="doc")],
        ...     ontology={"entities": [], "keywords": []},
        ...     vespa_hits=1,
        ... )
        >>> "# T-KEIR RAG Report" in report
        True
    """
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    detailed = detailed_report.strip() or build_fallback_detailed_report(
        focus_passages="",
        chunk_excerpts="",
    )
    if not detailed.startswith("##"):
        detailed = f"## Detailed Analysis\n\n{detailed}"

    sections = [
        "# T-KEIR RAG Report",
        "",
        f"- **Generated:** {timestamp}",
        f"- **Language:** {language}",
        f"- **Vespa hits:** {vespa_hits}",
        "",
        "## Question",
        "",
        query.strip(),
        "",
        "## Short Answer",
        "",
        short_answer.strip(),
        "",
        detailed,
        "",
        _ontology_section_markdown(ontology),
        "",
        _sources_section_markdown(chunks),
    ]
    return "\n".join(sections).strip() + "\n"
