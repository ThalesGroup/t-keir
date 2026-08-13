"""Title: Iterative chunk-by-chunk LLM Wiki builder.

Builds ``wiki.md`` by folding one evidence chunk at a time into the current
wiki (never discarding prior Answer / Evidence / Sources). Used by the
``okf_iterative_wiki`` orchestrator builtin.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

EVIDENCE_CHUNKS_FILENAME = "evidence_chunks.json"

# Clean markdown heading, or NLP-mangled "# # Information" / "Information".
_INFORMATION_HEADING_RE = re.compile(
    r"(?:^|\n)\s*(?:#+\s*)+#?\s*Information\b\s*",
    flags=re.IGNORECASE,
)

_DEFAULT_OKF_MERGE_SYSTEM = """\
You build a DETAILED OKF LLMWiki (Google OKF concept ``type: Wiki``) by folding
EVERY evidence chunk below into one wiki. Process chunks in order (1..N). Never
invent facts outside chunk text + Information metadata.

HARD RULES:
1. Output ONLY the full wiki markdown (YAML frontmatter + body).
2. Core sections required: Answer, Evidence, Sources, Gaps (plus Structured
   facts when seeded). Prefer Timeline / Actors & entities / Geospatial when
   grounded.
3. Answer must be a multi-paragraph synthesis of corpus facts — not a one-liner
   and not a restatement of the analyst request. Cover what / who / where /
   when / how known / so-what; note contradictions and confidence.
4. If a Structured facts checklist is present in the seed, fill grounded
   bullets with concrete multi-clause values (leave `_unknown_` when
   unsupported; cite chunk_id= on filled lines).
5. Evidence density: at least 2–4 atomic claims per contributing chunk when the
   text supports it (`- <claim text> (chunk_id=<id>)`).
6. Sources: `- chunk_id=<id> ← parent=<doc>` for every chunk_id used.
7. Prefer concrete entity / temporal / geospatial / numeric details from the
   chunks — do not thin-summarize away names, identifiers, or figures.
8. ## Information blocks are authoritative structured metadata — prefer them
   when filling Structured facts or Evidence.
"""


def seed_iterative_wiki(
    *,
    query: str,
    title: str | None = None,
    structured_facts_seed: str | None = None,
) -> str:
    """Return an OKF ``type: Wiki`` skeleton for ``query``.

    Core Google OKF LLMWiki shape: Answer / Evidence / Sources / Gaps.
    Optional ``structured_facts_seed`` (from a persona ``*_prompt`` agent)
    injects a Structured facts checklist between Answer and Evidence.

    Args:
        query: Analyst query driving the wiki title.
        title: Optional explicit title (defaults to ``query``).
        structured_facts_seed: Optional markdown block inserted after Answer.

    Returns:
        Full wiki markdown including YAML frontmatter.

    Example:
        >>> from thot.okf.iterative_wiki import seed_iterative_wiki
        >>> wiki = seed_iterative_wiki(query="Latakia Port")
        >>> "type: Wiki" in wiki and "## Answer" in wiki
        True
    """
    heading = (title or query or "Knowledge wiki").strip() or "Knowledge wiki"
    if len(heading) > 80:
        heading = heading[:77] + "…"
    from datetime import datetime, timezone

    lines = [
        "---",
        "type: Wiki",
        f"title: {heading}",
        "generated:",
        "  by: process:tkeir-okf-iterative-wiki",
        f"  at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "tkeir_okf_version: '0.2'",
        "---",
        f"# {heading}",
        "",
        "## Answer",
        "",
        "_OKF wiki — folding evidence chunks into Answer / Evidence / Sources._",
        "",
    ]
    facts = (structured_facts_seed or "").strip()
    if facts:
        lines.extend([facts, ""])
    lines.extend(
        [
            "## Evidence",
            "",
            "## Timeline",
            "",
            "_Filled by timeline persona: Events + Relations arrows._",
            "",
            "## Cross-source synthesis",
            "",
            "_Link claims across distinct sources; cite ≥2 chunk_ids per bullet._",
            "",
            "## Conjectures",
            "",
            "- _none grounded_",
            "",
            "## Sources",
            "",
            "## Gaps",
            "",
            "- Pending grounded evidence from retrieved chunks.",
            "",
        ]
    )
    return "\n".join(lines)


def split_narrative_and_information(text: str) -> tuple[str, str]:
    """Split chunk text into narrative body and ``## Information`` attrs.

    Handles clean ingest markdown and NLP-spaced headings
    (``# # Information``).

    Args:
        text: Raw chunk text from ingest or retrieval.

    Returns:
        ``(narrative, information)`` — either side may be empty.

    Example:
        >>> from thot.okf.iterative_wiki import split_narrative_and_information
        >>> split_narrative_and_information(
        ...     "Story here.\\n## Information\\n- **source:** x"
        ... )
        ('Story here.', '- **source:** x')
    """
    raw = (text or "").strip()
    if not raw:
        return "", ""
    match = _INFORMATION_HEADING_RE.search(raw)
    if not match:
        # Collapsed single-line form: "... ## Information - **source:** …"
        collapsed = re.search(
            r"(?:^|\s)(?:#+\s*)+#?\s*Information\b\s*",
            raw,
            flags=re.IGNORECASE,
        )
        if not collapsed:
            return raw, ""
        narrative = raw[: collapsed.start()].strip()
        information = raw[collapsed.end() :].strip()
        return narrative, information
    narrative = raw[: match.start()].strip()
    information = raw[match.end() :].strip()
    # Drop trailing sections after Information if another heading appears.
    next_heading = re.search(r"\n#{1,6}\s+\S", information)
    if next_heading and next_heading.start() > 20:
        information = information[: next_heading.start()].strip()
    return narrative, information


def compact_information_for_prompt(
    information: str,
    *,
    max_chars: int = 1400,
    priority_keys: list[str] | tuple[str, ...] | None = None,
) -> str:
    """Keep Information metadata short; optionally prioritize caller keys.

    Ranking is **use-case dependent** — pass persona/agent
    ``wiki_information_priority_keys`` (or equivalent). With no keys, line
    order is preserved and only ``max_chars`` truncation applies.

    Args:
        information: Raw ``## Information`` block text.
        max_chars: Maximum returned character count.
        priority_keys: Optional substrings whose lines are ranked first.
            Empty / ``None`` means no reordering.

    Returns:
        Trimmed information block, truncated with an ellipsis when needed.

    Example:
        >>> from thot.okf.iterative_wiki import compact_information_for_prompt
        >>> out = compact_information_for_prompt(
        ...     "- **evaluation:** high\\n- **misc:** filler",
        ...     max_chars=40,
        ...     priority_keys=["evaluation"],
        ... )
        >>> out.startswith("- **evaluation:**")
        True
    """
    text = (information or "").strip()
    if not text:
        return ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        out = text
    elif priority_keys:
        priority = tuple(priority_keys)
        ranked: list[str] = []
        rest: list[str] = []
        for line in lines:
            low = line.casefold()
            if any(key.casefold() in low for key in priority):
                ranked.append(line)
            else:
                rest.append(line)
        out = "\n".join(ranked + rest)
    else:
        out = "\n".join(lines)
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "\n…[information truncated]"
    return out


def normalize_evidence_chunk(raw: Any) -> dict[str, str] | None:
    """Normalize a chunk dict from RAG / search / HMI grab payloads.

    Extracts ``## Information`` into a dedicated ``information`` field and
    keeps narrative body in ``text_raw`` when possible.

    Args:
        raw: Chunk payload dict from retrieval or workflow params.

    Returns:
        Normalized chunk dict, or ``None`` when no usable content remains.

    Example:
        >>> from thot.okf.iterative_wiki import normalize_evidence_chunk
        >>> row = normalize_evidence_chunk({
        ...     "chunk_id": "c1",
        ...     "text_raw": "Narrative.\\n## Information\\n- **dtg:** today",
        ...     "parent_doc_id": "doc-1",
        ... })
        >>> row["chunk_id"]
        'c1'
        >>> "Narrative." in row["text_raw"]
        True
        >>> "dtg" in row["information"]
        True
    """
    if not isinstance(raw, dict):
        return None
    chunk_id = str(
        raw.get("chunk_id") or raw.get("id") or raw.get("passage_id") or ""
    ).strip()
    text = str(
        raw.get("text_raw") or raw.get("text") or raw.get("content") or ""
    ).strip()
    supplied_info = str(raw.get("information") or "").strip()
    narrative, extracted_info = split_narrative_and_information(text)
    information = supplied_info or extracted_info
    # If the chunk was Information-only, keep a short placeholder narrative.
    body = narrative.strip()
    if not body and information:
        body = "(metadata-only chunk — see Information block)"
    elif not body:
        body = text
    if not chunk_id and not body and not information:
        return None
    parent = str(
        raw.get("parent_doc_id")
        or raw.get("document_id")
        or raw.get("source_ref")
        or ""
    ).strip()
    title = str(raw.get("title") or "").strip()
    if not chunk_id:
        seed = (body or information)[:120]
        chunk_id = f"anon:{abs(hash(seed)) % 10_000_000}"
    return {
        "chunk_id": chunk_id,
        "parent_doc_id": parent,
        "title": title,
        "text_raw": body,
        "information": (
            compact_information_for_prompt(information) if information else ""
        ),
        "score": str(raw.get("score") or raw.get("relevance") or ""),
    }


def write_evidence_chunks(root: Path, chunks: list[dict[str, Any]]) -> Path:
    """Persist normalized evidence chunks next to wiki.md for iterative build.

    Args:
        root: OKF bundle directory.
        chunks: Raw chunk dicts from retrieval or workflow params.

    Returns:
        Path to the written ``evidence_chunks.json`` file.

    Example:
        >>> import json, tempfile
        >>> from pathlib import Path
        >>> from thot.okf.iterative_wiki import write_evidence_chunks
        >>> with tempfile.TemporaryDirectory() as td:
        ...     path = write_evidence_chunks(
        ...         Path(td),
        ...         [{"chunk_id": "c1", "text_raw": "Hello world."}],
        ...     )
        ...     payload = json.loads(path.read_text(encoding="utf-8"))
        ...     payload[0]["chunk_id"]
        'c1'
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in chunks:
        row = normalize_evidence_chunk(raw)
        if row is None:
            continue
        if row["chunk_id"] in seen:
            continue
        seen.add(row["chunk_id"])
        normalized.append(row)
    path = root / EVIDENCE_CHUNKS_FILENAME
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_evidence_chunks(root: Path) -> list[dict[str, str]]:
    """Load ``evidence_chunks.json`` from an OKF bundle root.

    Args:
        root: OKF bundle directory.

    Returns:
        List of normalized chunk dicts; empty when the file is missing.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.okf.iterative_wiki import load_evidence_chunks, write_evidence_chunks
        >>> with tempfile.TemporaryDirectory() as td:
        ...     root = Path(td)
        ...     _ = write_evidence_chunks(
        ...         root, [{"chunk_id": "c1", "text_raw": "Hello."}]
        ...     )
        ...     load_evidence_chunks(root)[0]["chunk_id"]
        'c1'
    """
    path = Path(root) / EVIDENCE_CHUNKS_FILENAME
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        LOGGER.warning("Failed to parse %s", path)
        return []
    if not isinstance(payload, list):
        return []
    out: list[dict[str, str]] = []
    for raw in payload:
        row = normalize_evidence_chunk(raw)
        if row is not None and (row.get("text_raw") or row.get("information")):
            out.append(row)
    return out


def chunks_from_params(params: dict[str, Any] | None) -> list[dict[str, str]]:
    """Read grab/search chunks passed on workflow params (HMI Reporter).

    Args:
        params: Workflow parameter dict; reads ``chunks`` or ``grab_chunks``.

    Returns:
        Deduplicated list of normalized chunk dicts.

    Example:
        >>> from thot.okf.iterative_wiki import chunks_from_params
        >>> rows = chunks_from_params(
        ...     {"chunks": [{"chunk_id": "c1", "text_raw": "Hi"}]}
        ... )
        >>> rows[0]["chunk_id"]
        'c1'
    """
    params = params or {}
    raw_list = params.get("chunks") or params.get("grab_chunks") or []
    if isinstance(raw_list, str):
        try:
            raw_list = json.loads(raw_list)
        except Exception:  # noqa: BLE001
            return []
    if not isinstance(raw_list, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in raw_list:
        row = normalize_evidence_chunk(raw)
        if row is None:
            continue
        if not row.get("text_raw") and not row.get("information"):
            continue
        if row["chunk_id"] in seen:
            continue
        seen.add(row["chunk_id"])
        out.append(row)
    return out


def enrich_chunks_with_sibling_information(
    chunks: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Merge ``information`` from same-parent siblings onto each chunk.

    Retrieval often splits narrative and ``## Information`` across golden
    chunks of the same parent document — fold them back for the LLM.

    Args:
        chunks: Normalized evidence chunk dicts.

    Returns:
        Copy of ``chunks`` with sibling information merged per parent.

    Example:
        >>> from thot.okf.iterative_wiki import enrich_chunks_with_sibling_information
        >>> chunks = [
        ...     {"chunk_id": "a", "parent_doc_id": "p1", "text_raw": "narr", "information": ""},
        ...     {"chunk_id": "b", "parent_doc_id": "p1", "text_raw": "", "information": "- **dtg:** today"},
        ... ]
        >>> out = enrich_chunks_with_sibling_information(chunks)
        >>> "dtg" in out[0]["information"]
        True
    """
    by_parent: dict[str, list[str]] = {}
    for chunk in chunks:
        parent = (chunk.get("parent_doc_id") or "").strip()
        info = (chunk.get("information") or "").strip()
        if not parent or not info:
            continue
        by_parent.setdefault(parent, []).append(info)
    if not by_parent:
        return chunks
    out: list[dict[str, str]] = []
    for chunk in chunks:
        parent = (chunk.get("parent_doc_id") or "").strip()
        merged = dict(chunk)
        sibs = by_parent.get(parent) or []
        if sibs:
            own = (chunk.get("information") or "").strip()
            parts = [own] if own else []
            for sib in sibs:
                if sib and sib not in parts:
                    parts.append(sib)
            merged["information"] = compact_information_for_prompt(
                "\n".join(parts)
            )
        out.append(merged)
    return out


def build_merge_prompt(
    *,
    query: str,
    current_wiki: str,
    chunk: dict[str, str],
    index: int,
    total: int,
) -> str:
    """User prompt for one iterative wiki merge step.

    Args:
        query: Analyst query or request text.
        current_wiki: Wiki markdown accumulated so far.
        chunk: Normalized evidence chunk for this step.
        index: One-based chunk index in the batch.
        total: Total chunks in the batch.

    Returns:
        Prompt string for a single merge LLM call.

    Example:
        >>> from thot.okf.iterative_wiki import build_merge_prompt
        >>> prompt = build_merge_prompt(
        ...     query="Q",
        ...     current_wiki="# W",
        ...     chunk={"chunk_id": "c1", "text_raw": "text"},
        ...     index=1,
        ...     total=2,
        ... )
        >>> "Chunk 1/2" in prompt
        True
    """
    text = chunk.get("text_raw") or ""
    # Keep prompts bounded while preserving substance.
    if len(text) > 6000:
        text = text[:6000] + "\n…[chunk truncated]"
    info = compact_information_for_prompt(chunk.get("information") or "")
    wiki = current_wiki or seed_iterative_wiki(query=query)
    if len(wiki) > 24000:
        wiki = (
            wiki[:24000]
            + "\n\n…[wiki truncated for context; preserve Sources]"
        )
    parts = [
        f"Analyst query / request:\n{query.strip()}",
        "",
        f"Chunk {index}/{total}",
        f"chunk_id: {chunk.get('chunk_id') or ''}",
        f"parent_doc_id: {chunk.get('parent_doc_id') or ''}",
        f"title: {chunk.get('title') or ''}",
        "",
        "Chunk narrative:",
        "-----",
        text,
        "-----",
    ]
    if info:
        parts.extend(
            [
                "",
                "## Information (structured metadata — authoritative):",
                "-----",
                info,
                "-----",
            ]
        )
    parts.extend(
        [
            "",
            "Current wiki (merge INTO this; do not shrink):",
            "===== WIKI START =====",
            wiki,
            "===== WIKI END =====",
            "",
            "Return the FULL updated wiki markdown only.",
        ]
    )
    return "\n".join(parts)


def extract_wiki_markdown(raw: str, *, fallback: str) -> str:
    """Pull wiki markdown out of an LLM response (fenced or bare).

    Args:
        raw: Raw LLM response text.
        fallback: Prior wiki markdown when extraction fails.

    Returns:
        Extracted wiki markdown, or ``fallback`` when none is detected.

    Example:
        >>> from thot.okf.iterative_wiki import extract_wiki_markdown
        >>> extract_wiki_markdown("```markdown\\n# Hi\\n```", fallback="fb")
        '# Hi'
    """
    text = (raw or "").strip()
    if not text:
        return fallback
    fence = re.search(
        r"```(?:markdown|md)?\s*\n([\s\S]*?)```",
        text,
        flags=re.IGNORECASE,
    )
    if fence:
        text = fence.group(1).strip()
    # Prefer content that looks like a wiki page.
    if (
        "## Answer" in text
        or "type: Wiki" in text
        or text.lstrip().startswith("#")
    ):
        return text
    if (
        "## Evidence" in text
        or "Structured facts (INTSUM" in text
        or "---" in text[:40]
    ):
        return text
    # Model returned prose only — keep prior wiki.
    LOGGER.warning(
        "Iterative wiki merge returned non-wiki payload; keeping prior"
    )
    return fallback


def ensure_osiris_panel_sections(wiki: str) -> str:
    """Ensure Timeline / Cross-source / Conjectures panels exist for the UI.

    When LLM folds timeout or strip sections, Osiris loses the highlighted
    panels. Re-inject empty placeholders before Sources/Gaps without wiping
    existing content.
    """
    text = (wiki or "").rstrip()
    if not text:
        return text

    def _has(heading: str) -> bool:
        return bool(
            re.search(rf"(?im)^##\s+{re.escape(heading)}\s*$", text)
        )

    inserts: list[tuple[str, str]] = []
    if not _has("Timeline") and not _has("Events"):
        inserts.append(
            (
                "Timeline",
                "## Timeline\n\n"
                "### Events\n\n"
                "- _pending dated events_\n\n"
                "### Relations\n\n"
                "- _pending arrows_\n",
            )
        )
    if not (
        _has("Cross-source synthesis")
        or _has("Event correlation")
        or _has("Cross-source")
    ):
        inserts.append(
            (
                "Cross-source synthesis",
                "## Cross-source synthesis\n\n"
                "- _pending multi-source links_\n",
            )
        )
    if not _has("Conjectures"):
        inserts.append(
            (
                "Conjectures",
                "## Conjectures\n\n- _none grounded_\n",
            )
        )
    if not inserts:
        return text + ("\n" if not text.endswith("\n") else "")

    block = "\n\n".join(body for _, body in inserts)
    # Insert before Sources or Gaps; else append.
    for anchor in (r"(?im)^##\s+Sources\b", r"(?im)^##\s+Gaps\b"):
        m = re.search(anchor, text)
        if m:
            return text[: m.start()].rstrip() + "\n\n" + block + "\n\n" + text[m.start() :]
    return text + "\n\n" + block + "\n"


def ensure_sources_section(wiki: str, chunks: list[dict[str, str]]) -> str:
    """Guarantee a Sources section listing every processed chunk_id.

    Args:
        wiki: Current wiki markdown.
        chunks: Evidence chunks whose ids should appear under Sources.

    Returns:
        Wiki markdown with missing ``chunk_id`` lines appended.

    Example:
        >>> from thot.okf.iterative_wiki import ensure_sources_section
        >>> wiki = ensure_sources_section("## Answer\\n\\nHi", [{"chunk_id": "c1"}])
        >>> "chunk_id=`c1`" in wiki
        True
    """
    text = (wiki or "").rstrip()
    if "## Sources" not in text:
        text = text + "\n\n## Sources\n"
    existing = text.lower()
    additions: list[str] = []
    for chunk in chunks:
        cid = chunk.get("chunk_id") or ""
        if not cid:
            continue
        needle = f"chunk_id={cid}".lower()
        alt = f"`{cid}`".lower()
        if needle in existing or alt in existing:
            continue
        parent = chunk.get("parent_doc_id") or ""
        if parent:
            additions.append(f"- chunk_id=`{cid}` ← parent=`{parent}`")
        else:
            additions.append(f"- chunk_id=`{cid}`")
    if not additions:
        return text + "\n"
    # Append before trailing Gaps if present, else at end of Sources.
    if "## Gaps" in text:
        head, gaps = text.split("## Gaps", 1)
        if not head.rstrip().endswith("\n"):
            head += "\n"
        return (
            head.rstrip() + "\n" + "\n".join(additions) + "\n\n## Gaps" + gaps
        )
    return text + "\n" + "\n".join(additions) + "\n"


def _chunk_narrative_budget(total_chunks: int) -> int:
    """Cap narrative chars so N chunks still fit one local-LLM generate call.

    Args:
        total_chunks: Number of evidence chunks in the batch.

    Returns:
        Per-chunk narrative character budget (between 1000 and 2800).

    Example:
        >>> from thot.okf.iterative_wiki import _chunk_narrative_budget
        >>> _chunk_narrative_budget(7)
        2000
        >>> _chunk_narrative_budget(1)
        2800
    """
    n = max(1, int(total_chunks or 1))
    # Aim for ≤ ~14k narrative chars across the batch (plus system + wiki seed).
    return max(1000, min(2800, 14000 // n))


def estimate_chars_to_tokens(chars: int) -> int:
    """Rough token estimate for English/OSINT prose (~4 chars/token)."""
    return max(1, int(chars) // 4)


def estimate_fold_prompt_chars(
    *,
    wiki_chars: int,
    chunk_count: int,
    max_chunk_chars: int,
    query_chars: int = 400,
    system_chars: int = 1800,
) -> int:
    """Estimate one cluster-fold prompt size (chars) before calling the LLM."""
    n = max(1, int(chunk_count))
    per = max(400, min(int(max_chunk_chars), 14000 // n))
    # Overhead: wrappers, headers, separators (~800) + per-chunk headers (~120).
    return (
        int(system_chars)
        + int(query_chars)
        + 800
        + max(0, int(wiki_chars))
        + n * (per + 120)
    )


def pack_clusters_for_llm_budget(
    clusters: list[list[dict[str, Any]]],
    *,
    wiki_chars: int,
    max_chunk_chars: int,
    prompt_char_budget: int = 14000,
    max_fold_calls: int = 3,
    query_chars: int = 400,
    system_chars: int = 1800,
) -> list[list[dict[str, Any]]]:
    """Merge agglomerative clusters into as few LLM fold calls as fit the budget.

    Quality rule: keep near-centroid chunks; only *pack* whole clusters together
    when the combined prompt stays under ``prompt_char_budget``. Cap the number
    of fold calls at ``max_fold_calls`` (timeline is a separate call).

    Example:
        >>> packs = pack_clusters_for_llm_budget(
        ...     [[{"chunk_id": "a", "text_raw": "x" * 200}]],
        ...     wiki_chars=500,
        ...     max_chunk_chars=800,
        ...     prompt_char_budget=14000,
        ... )
        >>> len(packs) == 1
        True
    """
    groups = [list(g) for g in clusters if g]
    if not groups:
        return []
    budget = max(6000, int(prompt_char_budget))
    max_calls = max(1, min(8, int(max_fold_calls)))

    def _fits(batch: list[dict[str, Any]], wiki_c: int) -> bool:
        return (
            estimate_fold_prompt_chars(
                wiki_chars=wiki_c,
                chunk_count=len(batch),
                max_chunk_chars=max_chunk_chars,
                query_chars=query_chars,
                system_chars=system_chars,
            )
            <= budget
        )

    # Later folds see a larger wiki — reserve less for evidence after call 1.
    packs: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    # Call 1 starts from a short seed; subsequent calls assume a grown wiki.
    wiki_for_pack = max(800, min(int(wiki_chars), budget // 3))

    for group in groups:
        candidate = current + list(group)
        if current and not _fits(candidate, wiki_for_pack):
            packs.append(current)
            current = list(group)
            # After first pack, assume wiki grew; shrink evidence room.
            wiki_for_pack = max(wiki_for_pack, min(budget // 2, max(wiki_chars, 4000)))
            if not _fits(current, wiki_for_pack):
                # Single huge cluster: still send it (fold will truncate per-chunk).
                packs.append(current)
                current = []
            if len(packs) >= max_calls:
                break
            continue
        if not current and not _fits(list(group), wiki_for_pack):
            packs.append(list(group))
            wiki_for_pack = max(wiki_for_pack, min(budget // 2, max(wiki_chars, 4000)))
            if len(packs) >= max_calls:
                break
            continue
        current = candidate

    if current and len(packs) < max_calls:
        packs.append(current)
    elif current and packs:
        # Overflow into last pack (fold truncates) rather than drop evidence.
        packs[-1].extend(current)

    # If we stopped early due to max_calls, fold remaining into the last pack.
    if len(packs) >= max_calls and groups:
        used_ids = {
            str(c.get("chunk_id") or id(c))
            for pack in packs
            for c in pack
        }
        leftover: list[dict[str, Any]] = []
        for group in groups:
            for c in group:
                key = str(c.get("chunk_id") or id(c))
                if key not in used_ids:
                    leftover.append(c)
                    used_ids.add(key)
        if leftover:
            packs[-1].extend(leftover)

    LOGGER.info(
        "fold packing: clusters=%s → packs=%s sizes=%s budget_chars=%s "
        "(~%s tokens in)",
        len(groups),
        len(packs),
        [len(p) for p in packs],
        budget,
        estimate_chars_to_tokens(budget),
    )
    return packs


def _format_chunk_block(
    chunk: dict[str, str],
    index: int,
    total: int,
    *,
    priority_keys: list[str] | tuple[str, ...] | None = None,
    max_chars: int | None = None,
) -> str:
    """Format one evidence chunk block for a merge or single-pass prompt.

    Args:
        chunk: Normalized evidence chunk dict.
        index: One-based chunk index in the batch.
        total: Total chunks in the batch.
        priority_keys: Optional Information priority keys for compaction.
        max_chars: Optional narrative override; defaults to batch budget.

    Returns:
        Markdown chunk block including narrative and Information metadata.

    Example:
        >>> from thot.okf.iterative_wiki import _format_chunk_block
        >>> block = _format_chunk_block(
        ...     {"chunk_id": "c1", "text_raw": "Hello"},
        ...     1,
        ...     1,
        ... )
        >>> "Chunk 1/1" in block
        True
    """
    text = chunk.get("text_raw") or ""
    budget = (
        int(max_chars)
        if max_chars and max_chars > 0
        else _chunk_narrative_budget(total)
    )
    if len(text) > budget:
        text = text[:budget] + "\n…[chunk truncated]"
    info = compact_information_for_prompt(
        chunk.get("information") or "",
        priority_keys=priority_keys,
    )
    lines = [
        f"### Chunk {index}/{total}",
        f"chunk_id: {chunk.get('chunk_id') or ''}",
        f"parent_doc_id: {chunk.get('parent_doc_id') or ''}",
        f"title: {chunk.get('title') or ''}",
        "narrative:",
        text,
    ]
    if info:
        lines.extend(["", "## Information (structured metadata):", info])
    lines.append("")
    return "\n".join(lines)


async def build_wiki_single_pass(
    *,
    llm: Any,
    query: str,
    chunks: list[dict[str, str]],
    temperature: float = 0.1,
    system: str | None = None,
    structured_facts_seed: str | None = None,
    information_priority_keys: list[str] | tuple[str, ...] | None = None,
) -> str:
    """One LLM call that folds all chunks (fast path for small result sets).

    Args:
        llm: Async LLM client exposing ``generate(prompt, ...)``.
        query: Analyst query or request text.
        chunks: Normalized evidence chunk dicts.
        temperature: Sampling temperature for the merge call.
        system: Optional system prompt override.
        structured_facts_seed: Optional Structured facts seed markdown.
        information_priority_keys: Optional Information compaction keys.

    Returns:
        Full wiki markdown after merge and Sources enforcement.

    Example:
        >>> import inspect
        >>> from thot.okf.iterative_wiki import build_wiki_single_pass
        >>> inspect.iscoroutinefunction(build_wiki_single_pass)
        True
    """
    usable = [
        c
        for c in enrich_chunks_with_sibling_information(chunks)
        if (c.get("text_raw") or "").strip()
        or (c.get("information") or "").strip()
    ]
    if not usable:
        return ensure_sources_section(
            seed_iterative_wiki(
                query=query, structured_facts_seed=structured_facts_seed
            ),
            [],
        )
    blocks = [
        _format_chunk_block(
            chunk,
            index,
            len(usable),
            priority_keys=information_priority_keys,
        )
        for index, chunk in enumerate(usable, start=1)
    ]
    skeleton = seed_iterative_wiki(
        query=query, structured_facts_seed=structured_facts_seed
    )
    prompt = "\n".join(
        [
            f"Analyst query / request:\n{query.strip()}",
            "",
            f"Fold these {len(usable)} evidence chunks into one OKF wiki "
            "(process in order; keep all citations; use Information metadata):",
            "",
            *blocks,
            "",
            "Start from this skeleton and expand it:",
            "===== WIKI START =====",
            skeleton,
            "===== WIKI END =====",
            "",
            "Return the FULL updated wiki markdown only.",
        ]
    )
    raw = await llm.generate(
        prompt,
        system=(system or "").strip() or _DEFAULT_OKF_MERGE_SYSTEM,
        temperature=temperature,
    )
    wiki = extract_wiki_markdown(
        str(raw or ""),
        fallback=skeleton,
    )
    return ensure_sources_section(wiki, usable)


_DEFAULT_WIKI_UPSERT_SYSTEM = """\
You UPDATE an existing OKF LLMWiki (type: Wiki) with NEW evidence only.
Keep the wiki compact. Prefer editing Answer / Structured facts / Evidence /
Sources over rewriting from scratch. Cite chunk_id= on new claims.
Output ONLY the full updated wiki markdown (YAML frontmatter + body).
Do not invent facts outside the provided wiki extract and new chunks.
"""


_DEFAULT_CHUNK_FOLD_SYSTEM = """\
You UPDATE an existing OKF LLMWiki by folding ONE new evidence chunk.
Preserve all prior grounded facts, citations, Timeline entries, and
Cross-source synthesis. Integrate new claims with chunk_id= citations.
Never invent hard facts. Prefer expanding Answer / Evidence / Timeline /
Cross-source synthesis / Conjectures over rewriting from scratch.
Strip any HTML, script, or image chrome from the chunk — keep prose only.
Output ONLY the full updated wiki markdown (YAML frontmatter + body).
"""


_DEFAULT_CLUSTER_FOLD_SYSTEM = """\
You UPDATE an existing OKF LLMWiki by folding ONE evidence CLUSTER
(semantically related chunks). Preserve prior grounded facts and citations.
Integrate every chunk in the cluster with chunk_id= cites. Prefer dated
claims in Answer / Evidence / Structured facts. Never invent hard facts.
Strip HTML/script/image chrome. Output ONLY the full updated wiki markdown.
"""


_DEFAULT_TIMELINE_SYSTEM = """\
You update ONLY the ## Timeline section of an OKF wiki: dated events plus
arrow relations (--> sequence, ==> depends, ~~> near). Preserve Answer /
Evidence / all other sections unchanged. Cite chunk_id= on every event and
arrow. Output the FULL wiki markdown.
"""


def _wiki_context_for_fold(current_wiki: str, *, max_chars: int) -> str:
    """Pass enough of the live wiki so iterative folds cannot drop Answer."""
    text = (current_wiki or "").strip()
    if not text:
        return "(empty wiki — start from seed structure)"
    budget = max(2000, int(max_chars))
    if len(text) <= budget:
        return text
    # Prefer keeping Answer + Structured facts + tail (Sources).
    from thot.okf.wiki_match import extract_wiki_sections

    head = extract_wiki_sections(text, max_chars=budget // 2, include_structured=True)
    tail = text[-(budget // 2) :].lstrip()
    return (
        head
        + "\n\n…[middle sections omitted for prompt budget]…\n\n"
        + tail
    )


async def fold_one_chunk_into_wiki(
    *,
    llm: Any,
    query: str,
    chunk: dict[str, str],
    current_wiki: str,
    index: int,
    total: int,
    temperature: float = 0.1,
    system: str | None = None,
    information_priority_keys: list[str] | tuple[str, ...] | None = None,
    max_chunk_chars: int = 2800,
    max_wiki_chars: int = 14000,
) -> str:
    """Fold a single evidence chunk into the current wiki (true iterative step)."""
    block = _format_chunk_block(
        chunk,
        index,
        total,
        priority_keys=information_priority_keys,
        max_chars=max_chunk_chars,
    )
    wiki_excerpt = _wiki_context_for_fold(
        current_wiki, max_chars=max(4000, int(max_wiki_chars))
    )
    prompt = "\n".join(
        [
            f"Analyst query / request:\n{query.strip()}",
            "",
            f"Fold evidence chunk {index}/{total} into the wiki. Keep prior "
            "content; add new grounded claims with dates when known.",
            "",
            "Current wiki (authoritative prior):",
            "===== WIKI START =====",
            wiki_excerpt,
            "===== WIKI END =====",
            "",
            "NEW evidence chunk:",
            block,
            "",
            "Return the FULL updated wiki markdown only.",
        ]
    )
    raw = await llm.generate(
        prompt,
        system=(system or "").strip() or _DEFAULT_CHUNK_FOLD_SYSTEM,
        temperature=temperature,
    )
    return extract_wiki_markdown(str(raw or ""), fallback=current_wiki)


async def fold_cluster_into_wiki(
    *,
    llm: Any,
    query: str,
    cluster: list[dict[str, str]],
    current_wiki: str,
    index: int,
    total: int,
    temperature: float = 0.1,
    system: str | None = None,
    information_priority_keys: list[str] | tuple[str, ...] | None = None,
    max_chunk_chars: int = 2200,
    max_wiki_chars: int = 14000,
) -> str:
    """Fold one BGE-clustered group of chunks into the wiki (one LLM call)."""
    n = max(1, len(cluster))
    per = max(800, min(int(max_chunk_chars), 14000 // n))
    blocks = [
        _format_chunk_block(
            chunk,
            i,
            n,
            priority_keys=information_priority_keys,
            max_chars=per,
        )
        for i, chunk in enumerate(cluster, start=1)
    ]
    wiki_excerpt = _wiki_context_for_fold(
        current_wiki, max_chars=max(5000, int(max_wiki_chars))
    )
    prompt = "\n".join(
        [
            f"Analyst query / request:\n{query.strip()}",
            "",
            f"Fold evidence CLUSTER {index}/{total} "
            f"({n} chunk(s) near the agglomerative cluster center) into a "
            "COMPREHENSIVE world-situation wiki. Expand ## Answer with "
            "multi-paragraph dated narrative covering what/who/where/when/"
            "so-what. Keep prior sections; emphasize dates / theatres.",
            "",
            "Current wiki (authoritative prior — preserve and enrich):",
            "===== WIKI START =====",
            wiki_excerpt,
            "===== WIKI END =====",
            "",
            "NEW evidence cluster:",
            *blocks,
            "",
            "Return the FULL updated wiki markdown only.",
        ]
    )
    system_prompt = (system or "").strip() or _DEFAULT_CLUSTER_FOLD_SYSTEM
    try:
        raw = await llm.generate(
            prompt,
            system=system_prompt,
            temperature=temperature,
        )
    except TimeoutError:
        # Local Ollama often stalls on huge fold prompts — retry once leaner.
        LOGGER.warning(
            "fold_cluster timeout cluster=%s/%s — retrying with truncated prompt",
            index,
            total,
        )
        lean_wiki = _wiki_context_for_fold(
            current_wiki, max_chars=max(3500, int(max_wiki_chars) // 2)
        )
        lean_per = max(500, min(900, per // 2))
        lean_blocks = [
            _format_chunk_block(
                chunk,
                i,
                n,
                priority_keys=information_priority_keys,
                max_chars=lean_per,
            )
            for i, chunk in enumerate(cluster, start=1)
        ]
        lean_prompt = "\n".join(
            [
                f"Analyst query:\n{query.strip()[:800]}",
                "",
                f"Fold CLUSTER {index}/{total} into the wiki. Keep ## Answer "
                "and prior sections; add dated facts only.",
                "",
                "===== WIKI START =====",
                lean_wiki,
                "===== WIKI END =====",
                "",
                "NEW evidence:",
                *lean_blocks,
                "",
                "Return FULL updated wiki markdown only.",
            ]
        )
        raw = await llm.generate(
            lean_prompt,
            system=system_prompt,
            temperature=temperature,
        )
    return extract_wiki_markdown(str(raw or ""), fallback=current_wiki)


def _section_body(markdown: str, heading: str) -> str | None:
    """Return body under ``## <heading>`` or None."""
    pattern = re.compile(
        rf"(?ims)^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s+|\Z)"
    )
    m = pattern.search(markdown or "")
    return m.group(1).strip() if m else None


def merge_timeline_into_wiki(prior_wiki: str, timeline_wiki: str) -> str:
    """Keep the situation report; splice ## Timeline from ``timeline_wiki``.

    If the timeline model dropped Answer / Evidence, restore them from
    ``prior_wiki`` instead of shipping an empty report.
    """
    prior = (prior_wiki or "").strip()
    updated = (timeline_wiki or "").strip()
    if not updated:
        return prior
    if not prior:
        return updated

    prior_answer = _section_body(prior, "Answer")
    updated_answer = _section_body(updated, "Answer")
    # Timeline-only (or Answer stripped) → graft Timeline into prior report.
    if prior_answer and not updated_answer:
        tl = _section_body(updated, "Timeline")
        if not tl and "## Timeline" in updated:
            # Whole body is mostly timeline.
            tl_m = re.search(
                r"(?ims)^##\s+Timeline\s*\n.*?(?=^##\s+Sources\b|\Z)",
                updated,
            )
            tl = tl_m.group(0).strip() if tl_m else updated
        else:
            tl = f"## Timeline\n\n{tl}" if tl else ""
        if not tl:
            return prior
        # Remove old Timeline from prior, insert before Sources (or append).
        base = re.sub(
            r"(?ims)^##\s+Timeline\s*\n.*?(?=^##\s+|\Z)",
            "",
            prior,
        ).rstrip()
        src_m = re.search(r"(?im)^##\s+Sources\b", base)
        if src_m:
            return (
                base[: src_m.start()].rstrip()
                + "\n\n"
                + tl.strip()
                + "\n\n"
                + base[src_m.start() :].lstrip()
            ).strip() + "\n"
        return (base + "\n\n" + tl.strip() + "\n").strip() + "\n"

    # Both have Answer — prefer longer narrative body.
    if prior_answer and updated_answer and len(prior_answer) > len(updated_answer) * 1.4:
        tl = _section_body(updated, "Timeline")
        if tl:
            return merge_timeline_into_wiki(
                prior, f"## Timeline\n\n{tl}\n"
            )
    return updated


async def build_timeline_pass(
    *,
    llm: Any,
    query: str,
    chunks: list[dict[str, str]],
    current_wiki: str,
    temperature: float = 0.1,
    system: str | None = None,
    information_priority_keys: list[str] | tuple[str, ...] | None = None,
    max_chunk_chars: int = 1600,
    max_wiki_chars: int = 24000,
    max_chunks: int = 24,
) -> str:
    """Second-pass LLM: build ## Timeline with event arrows; keep rest of wiki."""
    usable = [
        c
        for c in enrich_chunks_with_sibling_information(chunks)
        if (c.get("text_raw") or "").strip()
        or (c.get("information") or "").strip()
    ][: max(1, min(int(max_chunks), 40))]
    # Pass the FULL report (not Answer-only extract) so the model cannot
    # "forget" Answer / Evidence when rewriting.
    wiki_full = (current_wiki or "").strip()
    if len(wiki_full) > max(2000, int(max_wiki_chars)):
        wiki_full = wiki_full[: int(max_wiki_chars)].rstrip() + "\n…[truncated]"
    blocks = [
        _format_chunk_block(
            chunk,
            i,
            len(usable),
            priority_keys=information_priority_keys,
            max_chars=max_chunk_chars,
        )
        for i, chunk in enumerate(usable, start=1)
    ]
    prompt = "\n".join(
        [
            f"Analyst query / request:\n{query.strip()}",
            "",
            "Build / replace ## Timeline with dated Events and Relations "
            "arrows (--> sequence, ==> depends, ~~> near).",
            "CRITICAL: Return the FULL wiki. Preserve ## Answer, Structured "
            "facts, Evidence, Cross-source synthesis, Conjectures, Sources, "
            "Gaps verbatim — only add/replace ## Timeline.",
            "",
            "Current wiki (MUST be preserved except Timeline):",
            "===== WIKI START =====",
            wiki_full,
            "===== WIKI END =====",
            "",
            "Evidence chunks for dating and links:",
            *blocks,
            "",
            "Return the FULL updated wiki markdown only.",
        ]
    )
    raw = await llm.generate(
        prompt,
        system=(system or "").strip() or _DEFAULT_TIMELINE_SYSTEM,
        temperature=temperature,
    )
    updated = extract_wiki_markdown(str(raw or ""), fallback=current_wiki)
    return merge_timeline_into_wiki(current_wiki, updated)


async def build_wiki_upsert_pass(
    *,
    llm: Any,
    query: str,
    chunks: list[dict[str, str]],
    current_wiki: str,
    max_chunks: int = 4,
    max_chunk_chars: int = 900,
    max_wiki_chars: int = 3200,
    temperature: float = 0.1,
    system: str | None = None,
    structured_facts_seed: str | None = None,
    information_priority_keys: list[str] | tuple[str, ...] | None = None,
) -> str:
    """Single small LLM call: existing wiki + top-K delta chunks → updated wiki.

    Unlike ``build_wiki_single_pass`` / iterative fold, this keeps prompts small
    by clipping the current wiki and limiting chunk count/size.

    Example:
        >>> import inspect
        >>> from thot.okf.iterative_wiki import build_wiki_upsert_pass
        >>> inspect.iscoroutinefunction(build_wiki_upsert_pass)
        True
    """
    from thot.okf.wiki_match import extract_wiki_sections

    usable = [
        c
        for c in enrich_chunks_with_sibling_information(chunks)
        if (c.get("text_raw") or "").strip()
        or (c.get("information") or "").strip()
    ][: max(1, min(int(max_chunks), 12))]
    wiki_base = (current_wiki or "").strip()
    if not wiki_base:
        wiki_base = seed_iterative_wiki(
            query=query, structured_facts_seed=structured_facts_seed
        )
    wiki_excerpt = extract_wiki_sections(
        wiki_base, max_chars=max(400, int(max_wiki_chars))
    )
    if not usable:
        return ensure_sources_section(wiki_base, [])
    blocks = [
        _format_chunk_block(
            chunk,
            index,
            len(usable),
            priority_keys=information_priority_keys,
            max_chars=max_chunk_chars,
        )
        for index, chunk in enumerate(usable, start=1)
    ]
    prompt = "\n".join(
        [
            f"Analyst query / request:\n{query.strip()}",
            "",
            "Current wiki extract (authoritative prior; preserve grounded facts):",
            "===== WIKI EXTRACT START =====",
            wiki_excerpt,
            "===== WIKI EXTRACT END =====",
            "",
            f"NEW evidence ({len(usable)} chunks) — merge deltas only:",
            "",
            *blocks,
            "",
            "Return the FULL updated wiki markdown only.",
        ]
    )
    raw = await llm.generate(
        prompt,
        system=(system or "").strip() or _DEFAULT_WIKI_UPSERT_SYSTEM,
        temperature=temperature,
    )
    wiki = extract_wiki_markdown(str(raw or ""), fallback=wiki_base)
    return ensure_sources_section(wiki, usable)


async def build_wiki_iteratively(
    *,
    llm: Any,
    query: str,
    chunks: list[dict[str, str]],
    initial_wiki: str | None = None,
    max_chunks: int = 6,
    temperature: float = 0.1,
    on_progress: Any | None = None,
    system: str | None = None,
    structured_facts_seed: str | None = None,
    information_priority_keys: list[str] | tuple[str, ...] | None = None,
    sequential: bool = False,
    cluster: bool = False,
    cluster_similarity: float = 0.55,
    max_clusters: int = 8,
    max_chunk_chars: int = 2800,
    max_wiki_chars: int = 24000,
    prebuilt_clusters: list[list[dict[str, str]]] | None = None,
    per_cluster_for_llm: int = 5,
    prompt_char_budget: int = 14000,
    max_fold_calls: int = 3,
) -> str:
    """Fold chunks into a wiki via LLM.

    Modes:
      - ``cluster=True``: BGE agglomerative → pack clusters into ≤``max_fold_calls``
        LLM folds that fit ``prompt_char_budget`` (quality via near-centroids)
      - ``sequential=True``: one LLM call per chunk (slow; avoid for local LLMs)
      - else: single-pass merge over at most ``max_chunks``
    """
    # Hard cap raised: situation reports need enough textual material.
    capped = max(1, min(int(max_chunks or 6), 48))
    enriched = enrich_chunks_with_sibling_information(chunks)
    usable = [
        c
        for c in enriched
        if (c.get("text_raw") or "").strip()
        or (c.get("information") or "").strip()
    ][:capped]
    seed_kwargs = {"structured_facts_seed": structured_facts_seed}
    if not usable and not prebuilt_clusters:
        return ensure_sources_section(
            (initial_wiki or "").strip()
            or seed_iterative_wiki(query=query, **seed_kwargs),
            [],
        )

    if cluster:
        from thot.okf.chunk_cluster import cluster_chunks_agglomerative

        per_center = max(2, min(6, int(per_cluster_for_llm or 3)))
        if prebuilt_clusters:
            # Rare path: caller already clustered; still pick near-centroids.
            from thot.okf.chunk_cluster import select_near_centroids

            full = [
                [
                    c
                    for c in enrich_chunks_with_sibling_information(
                        [x for x in group if isinstance(x, dict)]
                    )
                    if (c.get("text_raw") or "").strip()
                    or (c.get("information") or "").strip()
                ]
                for group in prebuilt_clusters
                if group
            ]
            full = [g for g in full if g]
            clusters = select_near_centroids(full, per_cluster=per_center)
            LOGGER.info(
                "Wiki build: prebuilt clusters=%s → near-centroid fold sizes=%s",
                [len(g) for g in full],
                [len(g) for g in clusters],
            )
        else:
            # Design step 6: Wiki Agent BGE embed + agglomerative, then fold
            # only a few chunks nearest each cluster center.
            clusters = cluster_chunks_agglomerative(
                usable,
                similarity_threshold=cluster_similarity,
                max_clusters=max(1, int(max_clusters)),
                per_cluster_for_llm=per_center,
            )
            LOGGER.info(
                "Wiki build: agent agglomerative + near-centroid fold "
                "clusters=%s sizes=%s from %s chunks",
                len(clusters),
                [len(g) for g in clusters],
                len(usable),
            )
        if not clusters:
            clusters = [usable] if usable else []

        wiki = (initial_wiki or "").strip() or seed_iterative_wiki(
            query=query, **seed_kwargs
        )
        packs = pack_clusters_for_llm_budget(
            clusters,
            wiki_chars=len(wiki),
            max_chunk_chars=max_chunk_chars,
            prompt_char_budget=prompt_char_budget,
            max_fold_calls=max_fold_calls,
            query_chars=len(query or ""),
            system_chars=len(system or "") or 1800,
        )
        total = len(packs)
        folded: list[dict[str, str]] = []
        for i, group in enumerate(packs, start=1):
            # Later packs: shrink wiki context so more room stays for evidence.
            wiki_budget = (
                int(max_wiki_chars)
                if i == 1
                else max(4000, min(int(max_wiki_chars), int(prompt_char_budget) // 2))
            )
            try:
                wiki = await fold_cluster_into_wiki(
                    llm=llm,
                    query=query,
                    cluster=group,
                    current_wiki=wiki,
                    index=i,
                    total=total,
                    temperature=temperature,
                    system=system,
                    information_priority_keys=information_priority_keys,
                    max_chunk_chars=max_chunk_chars,
                    max_wiki_chars=wiki_budget,
                )
            except TimeoutError as exc:
                # Keep prior folds so Timeline / Cross-source panels survive.
                LOGGER.warning(
                    "fold pack %s/%s timed out — keeping partial wiki (%s chars): %s",
                    i,
                    total,
                    len(wiki or ""),
                    exc,
                )
                note = (
                    f"\n\n> _Fold pack {i}/{total} timed out; "
                    "prior sections retained._\n"
                )
                if note.strip() not in (wiki or ""):
                    wiki = (wiki or "") + note
                continue
            folded.extend(group)
            # Sources cite all usable golden chunks (URL refs), not only centers.
            wiki = ensure_sources_section(wiki, usable if usable else folded)
            if callable(on_progress):
                try:
                    on_progress(wiki, i, total)
                except Exception:  # noqa: BLE001
                    LOGGER.debug("on_progress failed", exc_info=True)
        return ensure_osiris_panel_sections(wiki)

    if sequential:
        LOGGER.info(
            "Wiki build: sequential fold over %s chunk(s) (cap=%s)",
            len(usable),
            capped,
        )
        wiki = (initial_wiki or "").strip() or seed_iterative_wiki(
            query=query, **seed_kwargs
        )
        total = len(usable)
        for i, chunk in enumerate(usable, start=1):
            wiki = await fold_one_chunk_into_wiki(
                llm=llm,
                query=query,
                chunk=chunk,
                current_wiki=wiki,
                index=i,
                total=total,
                temperature=temperature,
                system=system,
                information_priority_keys=information_priority_keys,
                max_chunk_chars=max_chunk_chars,
                max_wiki_chars=max_wiki_chars,
            )
            wiki = ensure_sources_section(wiki, usable[:i])
            if callable(on_progress):
                try:
                    on_progress(wiki, i, total)
                except Exception:  # noqa: BLE001
                    LOGGER.debug("wiki on_progress failed", exc_info=True)
        return ensure_sources_section(wiki, usable)

    LOGGER.info(
        "Wiki build: single-pass over %s chunk(s) (cap=%s)",
        len(usable),
        capped,
    )
    wiki = await build_wiki_single_pass(
        llm=llm,
        query=query,
        chunks=usable,
        temperature=temperature,
        system=system,
        structured_facts_seed=structured_facts_seed,
        information_priority_keys=information_priority_keys,
    )
    if callable(on_progress):
        try:
            on_progress(wiki, len(usable), len(usable))
        except Exception:  # noqa: BLE001
            LOGGER.debug("wiki on_progress failed", exc_info=True)
    return wiki


def create_evidence_bundle(
    *,
    user_space: str,
    query: str,
    chunks: list[dict[str, Any]],
    bundle_id: str | None = None,
    structured_facts_seed: str | None = None,
) -> tuple[str, Path]:
    """Create a minimal OKF bundle from grab/search chunks (no RAG export).

    Args:
        user_space: Vespa user space owning the bundle.
        query: Analyst query driving the seed wiki.
        chunks: Raw chunk dicts from grab or search.
        bundle_id: Optional explicit bundle id (UUID when omitted).
        structured_facts_seed: Optional Structured facts seed markdown.

    Returns:
        ``(bundle_id, bundle_root)``.

    Example:
        >>> import os, tempfile
        >>> from thot.okf.iterative_wiki import create_evidence_bundle
        >>> with tempfile.TemporaryDirectory() as td:
        ...     os.environ["TKEIR_WORKSPACE"] = td
        ...     bid, root = create_evidence_bundle(
        ...         user_space="dev@tkeir",
        ...         query="Test",
        ...         chunks=[{"chunk_id": "c1", "text_raw": "Hello world."}],
        ...         bundle_id="test-bundle",
        ...     )
        ...     ok = bid == "test-bundle" and (root / "wiki.md").is_file()
        ...     del os.environ["TKEIR_WORKSPACE"]
        ...     ok
        True
    """
    import uuid
    from datetime import datetime, timezone

    from thot.okf.exporter import OKF_VERSION, user_okf_root

    bid = (bundle_id or "").strip() or str(uuid.uuid4())
    root = user_okf_root(user_space) / bid
    root.mkdir(parents=True, exist_ok=True)
    (root / "chunks").mkdir(exist_ok=True)
    normalized = write_evidence_chunks(root, chunks)
    _ = normalized
    wiki = seed_iterative_wiki(
        query=query, structured_facts_seed=structured_facts_seed
    )
    (root / "wiki.md").write_text(wiki, encoding="utf-8")
    index = "\n".join(
        [
            "# OKF Bundle Index",
            "",
            f"- bundle_id: `{bid}`",
            f"- user_space: `{user_space}`",
            f"- tkeir_okf_version: {OKF_VERSION}",
            "- source: evidence_chunks (grab/search, no RAG export)",
            "",
            "## LLMWiki",
            "",
            "- [wiki](wiki.md) — iterative evidence wiki",
            "",
        ]
    )
    (root / "index.md").write_text(index + "\n", encoding="utf-8")
    meta = {
        "bundle": {
            "bundle_id": bid,
            "user_space": user_space,
            "query": query,
            "concept_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "path": str(root),
        },
        "concept_ids": [],
        "unfilled_docs": [],
        "evidence_only": True,
    }
    (root / ".tkeir-meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return bid, root
