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

# Default priority keys for compact_information_for_prompt (form-agnostic).
_DEFAULT_INFORMATION_PRIORITY_KEYS: tuple[str, ...] = (
    "evaluation",
    "admiralty",
    "location",
    "pir",
    "domain",
    "source_type",
    "source_category",
    "classification",
    "dtg",
    "originator",
    "correlation",
    "doc_id",
    "precedence",
    "mgrs",
    "country",
    "maritime",
    "kri",
    "risk",
    "jurisdiction",
)


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
    """
    heading = (title or query or "Knowledge wiki").strip() or "Knowledge wiki"
    if len(heading) > 80:
        heading = heading[:77] + "…"
    lines = [
        "---",
        "type: Wiki",
        f"title: {heading}",
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
    (``# # Information``). Returns ``(narrative, information)``.
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
    """Keep Information metadata short but retain key analyst fields."""
    text = (information or "").strip()
    if not text:
        return ""
    priority = (
        tuple(priority_keys)
        if priority_keys
        else _DEFAULT_INFORMATION_PRIORITY_KEYS
    )
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return text[:max_chars]
    ranked: list[str] = []
    rest: list[str] = []
    for line in lines:
        low = line.casefold()
        if any(key.casefold() in low for key in priority):
            ranked.append(line)
        else:
            rest.append(line)
    ordered = ranked + rest
    out = "\n".join(ordered)
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "\n…[information truncated]"
    return out


def normalize_evidence_chunk(raw: Any) -> dict[str, str] | None:
    """Normalize a chunk dict from RAG / search / HMI grab payloads.

    Extracts ``## Information`` into a dedicated ``information`` field and
    keeps narrative body in ``text_raw`` when possible.
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
    """Persist normalized evidence chunks next to wiki.md for iterative build."""
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
    """Load ``evidence_chunks.json`` from an OKF bundle root."""
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
    """Read grab/search chunks passed on workflow params (HMI Reporter)."""
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
    """User prompt for one iterative wiki merge step."""
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
    """Pull wiki markdown out of an LLM response (fenced or bare)."""
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


def ensure_sources_section(wiki: str, chunks: list[dict[str, str]]) -> str:
    """Guarantee a Sources section listing every processed chunk_id."""
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
    """Cap narrative chars so N chunks still fit one local-LLM generate call."""
    n = max(1, int(total_chunks or 1))
    # Aim for ≤ ~14k narrative chars across the batch (plus system + wiki seed).
    return max(1000, min(2800, 14000 // n))


def _format_chunk_block(
    chunk: dict[str, str],
    index: int,
    total: int,
    *,
    priority_keys: list[str] | tuple[str, ...] | None = None,
    max_chars: int | None = None,
) -> str:
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
    """One LLM call that folds all chunks (fast path for small result sets)."""
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
) -> str:
    """Fold chunks into a wiki via LLM.

    Default path is a **single** LLM call over at most ``max_chunks`` (6).
    Sequential per-chunk merges are intentionally avoided — they routinely
    exceed Reporter poll windows (15–30+ minutes for ~24 chunks).

    Persona ``*_prompt`` agents supply ``structured_facts_seed`` /
    ``system`` / ``information_priority_keys`` via the orchestrator.
    """
    # Hard cap: never fold more than 12 chunks even if caller asks for more.
    capped = max(1, min(int(max_chunks or 6), 12))
    enriched = enrich_chunks_with_sibling_information(chunks)
    usable = [
        c
        for c in enriched
        if (c.get("text_raw") or "").strip()
        or (c.get("information") or "").strip()
    ][:capped]
    seed_kwargs = {"structured_facts_seed": structured_facts_seed}
    if not usable:
        return ensure_sources_section(
            (initial_wiki or "").strip()
            or seed_iterative_wiki(query=query, **seed_kwargs),
            [],
        )

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

    Returns:
        ``(bundle_id, bundle_root)``.
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
