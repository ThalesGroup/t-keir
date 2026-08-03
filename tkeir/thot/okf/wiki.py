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
    """Collapse whitespace in an excerpt string.

    Args:
        text: Raw chunk or answer text.

    Returns:
        Single-line string with runs of whitespace collapsed.

    Example:
        >>> from thot.okf.wiki import _clean_excerpt
        >>> _clean_excerpt("  hello\\n  world  ")
        'hello world'
    """
    return re.sub(r"\s+", " ", (text or "").strip())


def _distinctive_query_phrases(query_text: str) -> list[str]:
    """Extract maximal capitalized spans from a query.

    Keeps short vessel prefixes (MT/MV/SS) and returns longest phrases first.

    Args:
        query_text: Analyst query or title text.

    Returns:
        Distinct lowercase phrases sorted by descending length.

    Example:
        >>> from thot.okf.wiki import _distinctive_query_phrases
        >>> _distinctive_query_phrases("MT Ever Given at Suez")
        ['mt ever given suez']
    """
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
    """Build a filesystem-safe slug from free text.

    Args:
        text: Source label or query.
        fallback: Value when ``text`` yields an empty slug.

    Returns:
        Lowercase slug capped at 80 characters.

    Example:
        >>> from thot.okf.wiki import _slugify
        >>> _slugify("Latakia Port!")
        'latakia_port'
    """
    cleaned = re.sub(r"[^A-Za-z0-9._\- ]+", "", (text or "").strip())
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._-")
    return (cleaned[:80] or fallback).lower()


def _looks_unavailable_answer(answer: str) -> bool:
    """Detect RAG answers that admit missing or unavailable information.

    Args:
        answer: LLM or RAG answer text.

    Returns:
        ``True`` when the answer is empty or matches an unavailable marker.

    Example:
        >>> from thot.okf.wiki import _looks_unavailable_answer
        >>> _looks_unavailable_answer("I don't know.")
        True
        >>> _looks_unavailable_answer("Latakia is a Syrian port.")
        False
    """
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
    """Extract entity and keyword bullet lines from a RAG ontology block.

    Args:
        rag_payload: Scoped RAG response payload.

    Returns:
        Tuple of entity markdown lines and plain keyword labels (each capped).

    Example:
        >>> from thot.okf.wiki import _ontology_lines
        >>> ents, kws = _ontology_lines({
        ...     "ontology": {
        ...         "entities": [{"label": "Latakia", "type": "Port"}],
        ...         "keywords": ["Syria"],
        ...     }
        ... })
        >>> ents[0]
        '- **Latakia** (Port)'
        >>> kws
        ['Syria']
    """
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
    """Keep ontology rows whose labels overlap distinctive query phrases.

    When nothing matches, returns truncated originals (8 entities / 12 keywords).
    Nested ``keep_label`` requires label overlap with the longest query phrase
    or sufficient token overlap for multi-token queries.

    Args:
        entities: Markdown entity bullet lines.
        keywords: Plain keyword strings.
        query: Analyst query used for phrase extraction.

    Returns:
        Filtered ``(entities, keywords)`` pair.

    Example:
        >>> from thot.okf.wiki import _filter_entities_to_query
        >>> ents = ["- **Latakia Port** (Location)", "- **Damascus** (City)"]
        >>> kws = ["Syria", "port"]
        >>> filtered_ents, _ = _filter_entities_to_query(
        ...     ents, kws, "Latakia Port"
        ... )
        >>> any("Latakia" in line for line in filtered_ents)
        True
        >>> all("Damascus" not in line for line in filtered_ents)
        True
    """
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
    """Build Evidence-section citation lines from RAG chunk hits.

    Prefers chunks whose text contains the longest distinctive query phrase;
    falls back to the first ``limit`` chunks when none match.

    Args:
        rag_payload: Scoped RAG response payload.
        query: Analyst query for phrase matching.
        limit: Maximum citation lines to return.

    Returns:
        Markdown bullet lines referencing chunk and parent ids.

    Example:
        >>> from thot.okf.wiki import _chunk_citation_lines
        >>> lines = _chunk_citation_lines(
        ...     {
        ...         "chunks": [{
        ...             "chunk_id": "c1",
        ...             "parent_doc_id": "doc-1",
        ...             "text_raw": "Latakia Port handles cargo.",
        ...         }]
        ...     },
        ...     "Latakia Port",
        ... )
        >>> lines[0].startswith("- `c1`")
        True
    """
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
    """Extractive fallback when the LLM answer is empty or unavailable.

    Concatenates up to five first sentences from chunks matching the query.

    Args:
        rag_payload: Scoped RAG response payload.
        query: Analyst query for phrase matching.

    Returns:
        Joined sentences, or empty string when no chunk matches.

    Example:
        >>> from thot.okf.wiki import _answer_from_matching_chunks
        >>> text = _answer_from_matching_chunks(
        ...     {
        ...         "chunks": [{
        ...             "text_raw": "Latakia Port is in Syria. It handles cargo.",
        ...         }]
        ...     },
        ...     "Latakia Port",
        ... )
        >>> "Latakia" in text
        True
    """
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
    """Build frontmatter and body for an LLMWiki page.

    Args:
        query: Analyst query driving title and filtering.
        user_space: Vespa user space owning the bundle.
        rag_payload: Optional scoped RAG response (answer, ontology, chunks).
        concept_ids: Related OKF concept ids for cross-links.
        bundle_id: Bundle identifier for the Sources section.

    Returns:
        ``(frontmatter, markdown_body)`` ready for ``wiki.md``.

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

    from thot.okf.models import OkfActorEvent

    fm = OkfConceptFrontmatter(
        type="Wiki",
        title=title,
        description=first_sentence(answer or query),
        resource=None,
        tags=["llmwiki", "okf", "wiki"],
        timestamp=datetime.now(timezone.utc),
        generated=OkfActorEvent(
            by="process:tkeir-okf-wiki",
            at=datetime.now(timezone.utc),
        ),
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
    """Write ``wiki.md`` into an OKF bundle and link it from ``index.md``.

    Args:
        bundle_root: OKF bundle directory.
        query: Analyst query.
        user_space: Vespa user space owning the bundle.
        rag_payload: Optional scoped RAG response.
        concept_ids: Related OKF concept ids for cross-links.
        bundle_id: Bundle identifier for the Sources section.

    Returns:
        Path to the written ``wiki.md`` file.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.okf.wiki import write_llm_wiki
        >>> with tempfile.TemporaryDirectory() as td:
        ...     path = write_llm_wiki(
        ...         Path(td),
        ...         query="Latakia Port",
        ...         user_space="dev@tkeir",
        ...         rag_payload={"answer": "Latakia is a Syrian port."},
        ...     )
        ...     path.name
        'wiki.md'
    """
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
    """Default personal-space path for a published wiki page.

    Args:
        query: Analyst query used to derive the slug.

    Returns:
        Relative path under ``wiki/`` ending in ``.md``.

    Example:
        >>> from thot.okf.wiki import suggested_workspace_wiki_path
        >>> suggested_workspace_wiki_path("Latakia Port")
        'wiki/latakia_port.md'
    """
    return f"wiki/{_slugify(query)}.md"
