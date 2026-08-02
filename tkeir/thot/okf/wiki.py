"""Title: OKF / LLMWiki page builder.

Build a wiki-style Markdown page (OKF concept ``type: Wiki``) from a scoped
export: query, RAG answer, ontology highlights, and concept/chunk links.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from thot.okf.exporter import OKF_VERSION, _write_concept_file, first_sentence
from thot.okf.models import OkfConceptFrontmatter


def _clean_excerpt(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _distinctive_query_phrases(query_text: str) -> list[str]:
    """Maximal capitalized spans, keeping short vessel prefixes (MT/MV/SS)."""
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'._-]*", query_text or "")
    cleaned_tokens: list[str] = []
    for token in tokens:
        token = token.strip("._-")
        if not token:
            continue
        if len(token) >= 3 or (len(token) == 2 and token.isupper()):
            cleaned_tokens.append(token)
    tokens = cleaned_tokens
    phrases: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token[:1].isupper():
            end = index + 1
            while end < len(tokens) and tokens[end][:1].isupper():
                end += 1
            if end - index >= 2:
                phrases.append(" ".join(tokens[index:end]).lower())
            index = end
            continue
        index += 1
    phrases.sort(key=len, reverse=True)
    return list(dict.fromkeys(phrases))


def _slugify(text: str, *, fallback: str = "wiki") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._\- ]+", "", (text or "").strip())
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._-")
    return (cleaned[:80] or fallback).lower()


def _looks_unavailable_answer(answer: str) -> bool:
    text = (answer or "").strip().lower()
    if not text:
        return True
    markers = (
        "information is not available",
        "does not have information",
        "no information about",
        "no relevant information",
        "cannot find information",
        "i don't know",
        "i do not know",
    )
    return any(marker in text for marker in markers)


def _ontology_lines(
    rag_payload: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Extract entity / keyword bullet lines from a RAG response ontology."""
    ontology = rag_payload.get("ontology") or {}
    if not isinstance(ontology, dict):
        return [], []
    entities: list[str] = []
    for row in ontology.get("entities") or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()
        etype = str(row.get("type") or "Entity").strip()
        if label:
            entities.append(f"- **{label}** ({etype})")
    keywords: list[str] = []
    for row in ontology.get("keywords") or []:
        if isinstance(row, dict):
            label = str(row.get("label") or "").strip()
        else:
            label = str(row or "").strip()
        if label:
            keywords.append(label)
    return entities[:24], keywords[:24]


def _filter_entities_to_query(
    entities: list[str], keywords: list[str], query: str
) -> tuple[list[str], list[str]]:
    phrases = _distinctive_query_phrases(query)
    if not phrases:
        return entities, keywords
    longest = phrases[0]
    tokens = {t for t in longest.split() if len(t) > 2}

    def keep_label(line: str) -> bool:
        label = line
        if "**" in line:
            match = re.search(r"\*\*(.+?)\*\*", line)
            label = match.group(1) if match else line
        hay = label.lower()
        if longest in hay:
            return True
        parts = longest.split()
        if len(parts) >= 2 and " ".join(parts[-2:]) in hay:
            return True
        overlap = sum(1 for token in tokens if token in hay)
        if len(tokens) >= 3:
            return overlap >= 3
        return overlap >= min(2, len(tokens))

    filtered_entities = [line for line in entities if keep_label(line)]
    filtered_keywords = [
        kw
        for kw in keywords
        if keep_label(kw) or any(token in kw.lower() for token in tokens)
    ]
    return (
        filtered_entities or entities[:8],
        filtered_keywords or keywords[:12],
    )


def _chunk_citation_lines(
    rag_payload: dict[str, Any], query: str, limit: int = 12
) -> list[str]:
    phrases = _distinctive_query_phrases(query)
    longest = phrases[0] if phrases else ""
    lines: list[str] = []
    fallback: list[str] = []
    for chunk in rag_payload.get("chunks") or []:
        if not isinstance(chunk, dict):
            continue
        cid = str(chunk.get("chunk_id") or chunk.get("id") or "").strip()
        parent = str(
            chunk.get("parent_doc_id") or chunk.get("document_id") or ""
        ).strip()
        excerpt = str(chunk.get("text_raw") or chunk.get("text") or "").strip()
        cleaned = _clean_excerpt(excerpt)
        excerpt_one_line = cleaned[:180]
        if not cid and not excerpt_one_line:
            continue
        head = cid or parent or "chunk"
        if parent and parent != head:
            line = f"- `{head}` ← `{parent}` — {excerpt_one_line}"
        else:
            line = f"- `{head}` — {excerpt_one_line}"
        if longest and longest in cleaned.lower():
            lines.append(line)
        else:
            fallback.append(line)
        if len(lines) >= limit:
            break
    return (lines or fallback)[:limit]


def _answer_from_matching_chunks(
    rag_payload: dict[str, Any], query: str
) -> str:
    """Extractive fallback when the LLM answer is empty / unavailable."""
    phrases = _distinctive_query_phrases(query)
    longest = phrases[0] if phrases else ""
    sentences: list[str] = []
    for chunk in rag_payload.get("chunks") or []:
        if not isinstance(chunk, dict):
            continue
        text = _clean_excerpt(
            str(chunk.get("text_raw") or chunk.get("text") or "")
        )
        if longest and longest not in text.lower():
            continue
        sentence = first_sentence(text)
        if sentence and sentence not in sentences:
            sentences.append(sentence)
        if len(sentences) >= 5:
            break
    if not sentences:
        return ""
    return " ".join(sentences)


def build_llm_wiki_markdown(
    *,
    query: str,
    user_space: str,
    rag_payload: dict[str, Any] | None = None,
    concept_ids: list[str] | None = None,
    bundle_id: str | None = None,
) -> tuple[OkfConceptFrontmatter, str]:
    """Build frontmatter + body for an LLMWiki page.

    Example:
        >>> fm, body = build_llm_wiki_markdown(
        ...     query="Latakia Port",
        ...     user_space="dev@tkeir",
        ...     rag_payload={"answer": "Latakia is a Syrian port."},
        ... )
        >>> fm.type
        'Wiki'
        >>> "Latakia" in body
        True
    """
    payload = rag_payload if isinstance(rag_payload, dict) else {}
    answer = str(
        payload.get("answer")
        or payload.get("report_markdown")
        or payload.get("short_answer")
        or ""
    ).strip()
    if _looks_unavailable_answer(answer):
        recovered = _answer_from_matching_chunks(payload, query)
        if recovered:
            answer = recovered
    title = (query or "Knowledge wiki").strip()
    phrases = _distinctive_query_phrases(query)
    if phrases and len(title) > 48:
        title = phrases[0].upper()
    entities, keywords = _ontology_lines(payload)
    entities, keywords = _filter_entities_to_query(entities, keywords, query)
    citations = _chunk_citation_lines(payload, query)
    concepts = [str(c).strip() for c in concept_ids or [] if str(c).strip()]

    fm = OkfConceptFrontmatter(
        type="Wiki",
        title=title,
        description=first_sentence(answer or query),
        resource=None,
        tags=["llmwiki", "okf", "wiki"],
        timestamp=datetime.now(timezone.utc),
        tkeir_doc_id=f"wiki:{_slugify(title)}",
        tkeir_user_space=user_space,
        tkeir_chunk_ids=[],
        tkeir_okf_version=OKF_VERSION,
    )

    body_parts = [
        f"# {title}",
        "",
        "> OKF / LLMWiki page generated from a scoped RAG query.",
        "",
        "## Query",
        "",
        query.strip() or "_No query._",
        "",
        "## Executive summary",
        "",
        answer or "_No grounded answer was returned by RAG._",
        "",
    ]
    if entities:
        body_parts.extend(["## Key entities", "", *entities, ""])
    if keywords:
        body_parts.extend(
            [
                "## Keywords",
                "",
                ", ".join(keywords),
                "",
            ]
        )
    if concepts:
        body_parts.extend(
            [
                "## OKF concepts",
                "",
                *[f"- [{cid}](concepts/{cid}.md)" for cid in concepts],
                "",
            ]
        )
    if citations:
        body_parts.extend(["## Evidence", "", *citations, ""])
    body_parts.extend(
        [
            "## Sources",
            "",
            f"- Bundle: `{bundle_id or 'unknown'}`",
            f"- User space: `{user_space}`",
            "- Related: [query_context.md](query_context.md), [index.md](index.md)",
            "",
        ]
    )
    return fm, "\n".join(body_parts)


def write_llm_wiki(
    bundle_root: Path,
    *,
    query: str,
    user_space: str,
    rag_payload: dict[str, Any] | None = None,
    concept_ids: list[str] | None = None,
    bundle_id: str | None = None,
) -> Path:
    """Write ``wiki.md`` into an OKF bundle and link it from ``index.md``."""
    root = Path(bundle_root)
    fm, body = build_llm_wiki_markdown(
        query=query,
        user_space=user_space,
        rag_payload=rag_payload,
        concept_ids=concept_ids,
        bundle_id=bundle_id or root.name,
    )
    wiki_path = root / "wiki.md"
    _write_concept_file(wiki_path, fm, body)

    index_path = root / "index.md"
    if index_path.is_file():
        text = index_path.read_text(encoding="utf-8")
        if "wiki.md" not in text:
            index_path.write_text(
                text.rstrip()
                + "\n\n## LLMWiki\n\n- [wiki](wiki.md) — generated knowledge page\n",
                encoding="utf-8",
            )
    return wiki_path


def suggested_workspace_wiki_path(query: str) -> str:
    """Default personal-space path for a published wiki page."""
    return f"wiki/{_slugify(query)}.md"
