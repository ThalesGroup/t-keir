"""Title: NLP forge — open Osiris seed URLs → clean → SVO/keywords → SearX queries.

Also builds root documents that must stay first for wiki generation, and
optionally persists forged queries under the workspace.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from thot.tools.collector.config import CollectorSettings
from thot.tools.collector.convert import bytes_to_markdown, clean_markdown
from thot.tools.collector.forge import (
    categories_for_api,
    diversify_seeds,
    forge_searx_query,
    sharpen_query,
)
from thot.tools.collector.forge_config import ForgeConfig, load_forge_config
from thot.tools.collector.service import fetch_url_bytes, markdown_filename
from thot.tools.collector.wiki_loop import paragraph_chunks

LOGGER = logging.getLogger(__name__)

_HTTP_RE = re.compile(r"^https?://", re.I)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash_id(raw: str) -> str:
    import hashlib

    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def save_forged_queries(
    workspace: Path,
    queries: list[dict[str, Any]],
    *,
    enabled: bool = True,
    label: str = "feed",
) -> Path | None:
    """Write forged queries as JSONL under ``workspace/collector/forged_queries/``.

    When ``enabled`` is false, returns ``None`` without writing.
    """
    if not enabled:
        return None
    if not queries:
        return None
    out_dir = Path(workspace) / "collector" / "forged_queries"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"{label}_{stamp}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for row in queries:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    LOGGER.info("saved %s forged queries → %s", len(queries), path)
    return path


def _synthetic_markdown(seed: dict[str, Any]) -> str:
    """Fallback root body when the seed has no fetchable URL."""
    title = str(seed.get("title") or "").strip() or "Osiris event"
    snippet = str(seed.get("snippet") or "").strip()
    place = str(seed.get("place") or "").strip()
    api = str(seed.get("api") or "osiris").strip()
    lines = [
        f"# {title}",
        "",
        f"_Osiris seed · {api}_",
        "",
    ]
    if place:
        lines.append(f"**Place:** {place}")
        lines.append("")
    if snippet:
        lines.append(snippet)
        lines.append("")
    return "\n".join(lines).strip()


async def fetch_seed_markdown(
    seed: dict[str, Any],
    settings: CollectorSettings,
    *,
    timeout_s: float,
    max_chars: int,
) -> tuple[str, str, bool]:
    """Return ``(markdown, url, fetched)`` for a seed.

    Opens the Osiris feed URL when present; otherwise builds synthetic text.
    """
    url = str(seed.get("url") or "").strip()
    if not url or not _HTTP_RE.match(url):
        return _synthetic_markdown(seed), "", False
    try:
        raw, filename, ctype = await fetch_url_bytes(
            url,
            timeout_s=timeout_s,
            user_agent=settings.user_agent,
        )
        body = bytes_to_markdown(raw, filename=filename, content_type=ctype)
        body = clean_markdown(body)
        if len(body) > max_chars:
            body = body[:max_chars].rsplit("\n", 1)[0] + "\n"
        if not body.strip():
            return _synthetic_markdown(seed), url, False
        return body, url, True
    except Exception as exc:  # noqa: BLE001
        LOGGER.info("seed fetch failed %s: %s", url, exc)
        return _synthetic_markdown(seed), url, False


def _nlp_signals_from_text(text: str) -> dict[str, Any]:
    """Reuse collector ontology NLP helpers (pipeline or heuristic)."""
    from thot.tools.collector.ontology_wiki import (
        _analyze_text_pipeline,
        _fallback_extract_signals,
        _merge_pipeline_signals,
    )

    pipeline = _analyze_text_pipeline(text[:6000])
    heuristic = _fallback_extract_signals(
        text,
        [{"title": "", "text_raw": text[:2000], "chunk_id": "seed"}],
    )
    return _merge_pipeline_signals(pipeline, heuristic)


def _important_expressions(signals: dict[str, Any], *, limit: int = 8) -> list[str]:
    """Rank NER + keywords as short searchable expressions (drop chrome junk)."""
    junk = re.compile(
        r"(?i)^(https?://|www\.|telegram|widget|\.js$|download|context|"
        r"cookie|privacy|subscribe|follow us|click here|menu|login)"
    )
    scored: list[tuple[float, str]] = []
    seen: set[str] = set()
    for i, ent in enumerate(signals.get("ner_entities") or []):
        if not isinstance(ent, dict):
            continue
        label = str(ent.get("text") or "").strip()
        key = label.casefold()
        if len(label) < 2 or key in seen:
            continue
        if junk.search(label) or "." in label and label.lower().endswith(
            (".js", ".css", ".png", ".jpg", ".svg")
        ):
            continue
        seen.add(key)
        scored.append((100 - i, label))
    for i, kw in enumerate(signals.get("keywords") or []):
        label = str(kw).strip()
        key = label.casefold()
        if len(label) < 2 or key in seen:
            continue
        if junk.search(label) or label.count(".") >= 1 and " " not in label:
            continue
        seen.add(key)
        scored.append((50 - i, label))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [lab for _, lab in scored[:limit]]


def _resolve_seed_place(
    seed: dict[str, Any],
    *,
    forge_cfg: ForgeConfig,
    settings: CollectorSettings | None = None,
) -> str:
    """Prefer existing place; else reverse-geocode coords → region/country."""
    place = str(seed.get("place") or "").strip()
    if place and not re.fullmatch(r"-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?", place):
        return place
    coords = seed.get("coords")
    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
        return ""
    from thot.tools.collector.geocode import place_from_coords

    geo = {
        "enabled": forge_cfg.geocode.enabled,
        "url": forge_cfg.geocode.url,
        "timeout_s": forge_cfg.geocode.timeout_s,
        "cache": forge_cfg.geocode.cache,
    }
    ua = settings.user_agent if settings else "tkeir-collector/2.0"
    ws = settings.workspace if settings else None
    return place_from_coords(
        list(coords), forge_geocode=geo, user_agent=ua, workspace=ws
    )


def queries_from_signals(
    seed: dict[str, Any],
    signals: dict[str, Any],
    *,
    forge_cfg: ForgeConfig,
    max_queries: int,
    settings: CollectorSettings | None = None,
) -> list[dict[str, Any]]:
    """Build SearXNG queries from title/snippet + SVO + place (no -porn spam)."""
    api = str(seed.get("api") or "osiris")
    title = str(seed.get("title") or "").strip()
    snippet = str(seed.get("snippet") or "").strip()
    place = _resolve_seed_place(seed, forge_cfg=forge_cfg, settings=settings)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    nlp = forge_cfg.nlp

    def _emit(core: str, *, priority: float, kind: str) -> None:
        if len(out) >= max_queries:
            return
        # Title / snippet are mandatory anchors when present.
        parts: list[str] = []
        if title and nlp.require_title_or_snippet:
            parts.append(title)
        elif snippet and nlp.require_title_or_snippet:
            parts.append(snippet[:180])
        if core and core.casefold() not in (title or "").casefold():
            parts.append(core)
        if not parts and snippet:
            parts.append(snippet[:180])
        if not parts:
            return
        q = forge_searx_query(
            title=parts[0],
            place=place,
            type_hint="",
            extra=" ".join(parts[1:]) if len(parts) > 1 else "",
        )
        if not q:
            return
        sharpened = sharpen_query(api, q)
        key = sharpened.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(
            {
                "id": f"{api}-nlp-{_hash_id(str(seed.get('parent_id')) + sharpened)}",
                "query": sharpened,
                "api": api,
                "source": str(seed.get("source") or ""),
                "timestamp": seed.get("timestamp"),
                "snippet": seed.get("snippet"),
                "title": (title or core)[:160],
                "priority": float(seed.get("priority") or 0) + priority,
                "coords": seed.get("coords"),
                "place": place,
                "streamedAt": _now_iso(),
                "categories": categories_for_api(api),
                "forge_kind": kind,
                "root_url": str(seed.get("url") or ""),
                "root_parent_id": str(seed.get("parent_id") or ""),
            }
        )

    # Always emit at least one title/snippet-based query first.
    if title or snippet:
        _emit("", priority=40, kind="title_snippet")

    if nlp.use_svo:
        for triple in signals.get("svo_triples") or []:
            if not isinstance(triple, dict):
                continue
            subj = str(triple.get("subject") or "").strip()
            verb = str(triple.get("verb") or "").strip()
            obj = str(triple.get("object") or "").strip()
            if not subj or not verb:
                continue
            phrase = " ".join(p for p in (subj, verb, obj) if p)
            _emit(phrase, priority=30, kind="svo")
            if len(out) >= max_queries:
                return out

    if nlp.use_keywords:
        exprs = _important_expressions(signals)
        if exprs:
            _emit(" ".join(exprs[:3]), priority=20, kind="keywords")
        for expr in exprs[: max_queries]:
            _emit(expr, priority=12, kind="expression")
            if len(out) >= max_queries:
                break

    if not out and (title or snippet):
        _emit(title or snippet[:120], priority=5, kind="title_fallback")
    return out


def root_document_from_seed(
    seed: dict[str, Any],
    markdown: str,
    *,
    url: str,
    fetched: bool,
) -> dict[str, Any]:
    """Build the pinned root document for wiki / map."""
    title = str(seed.get("title") or "").strip() or (url or "Osiris seed")
    synthetic_url = url or f"osiris://seed/{seed.get('parent_id') or _hash_id(title)}"
    return {
        "url": synthetic_url,
        "title": title,
        "snippet": str(seed.get("snippet") or "")[:400],
        "engine": "osiris-seed",
        "topic": f"osiris/{seed.get('api') or 'osiris'}",
        "query": f"[root] {title}",
        "filename": markdown_filename(synthetic_url, title),
        "markdown_chars": len(markdown or ""),
        "markdown": markdown or _synthetic_markdown(seed),
        "collected_at": _now_iso(),
        "is_root": True,
        "root_seed": True,
        "fetched": fetched,
        "queryId": seed.get("parent_id"),
        "queryApi": seed.get("api"),
        "querySource": seed.get("source"),
        "lat": (seed.get("coords") or [None, None])[0]
        if isinstance(seed.get("coords"), list)
        else None,
        "lng": (seed.get("coords") or [None, None])[1]
        if isinstance(seed.get("coords"), list)
        else None,
        "anchorLat": (seed.get("coords") or [None, None])[0]
        if isinstance(seed.get("coords"), list)
        else None,
        "anchorLng": (seed.get("coords") or [None, None])[1]
        if isinstance(seed.get("coords"), list)
        else None,
    }


def _absorb_queries(
    forged: list[dict[str, Any]],
    *,
    queries: list[dict[str, Any]],
    seen_q: set[str],
    cap: int,
) -> None:
    for row in forged:
        if len(queries) >= cap:
            return
        key = str(row.get("query") or "").lower()
        if not key or key in seen_q:
            continue
        seen_q.add(key)
        queries.append(row)


async def forge_queries_from_osiris_seeds_nlp(
    settings: CollectorSettings,
    seeds: list[dict[str, Any]],
    *,
    max_queries: int = 40,
    forge_cfg: ForgeConfig | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Forge from seed title/snippet first; optionally enrich via URL fetch + NLP.

    Root documents stay ordered to match selected seeds (wiki pin).
    Seeds are diversified across API families so one layer cannot monopolize.
    """
    cfg = forge_cfg or load_forge_config()
    nlp = cfg.nlp
    cap = min(max(1, max_queries), nlp.max_queries_total)
    selected = diversify_seeds(seeds, max_seeds=nlp.max_seeds)

    queries: list[dict[str, Any]] = []
    roots: list[dict[str, Any]] = []
    seen_q: set[str] = set()

    # Fast path: title/snippet queries without waiting on HTTP (covers malware
    # IPs and broken feed URLs). One query per seed keeps the batch broad.
    for seed in selected:
        if len(queries) >= cap:
            break
        per_seed = min(1, nlp.max_queries_per_seed, cap - len(queries))
        forged = queries_from_signals(
            seed,
            {},
            forge_cfg=cfg,
            max_queries=per_seed,
            settings=settings,
        )
        _absorb_queries(forged, queries=queries, seen_q=seen_q, cap=cap)

    # Parallel fetch seed URLs for root docs + optional SVO/keyword enrichment.
    fetch_targets = [
        s
        for s in selected
        if str(s.get("url") or "").strip() and _HTTP_RE.match(str(s.get("url") or ""))
    ]

    async def _one(seed: dict[str, Any]) -> tuple[dict[str, Any], str, str, bool]:
        md, url, fetched = await fetch_seed_markdown(
            seed,
            settings,
            timeout_s=nlp.fetch_timeout_s,
            max_chars=nlp.max_chars,
        )
        return seed, md, url, fetched

    fetched_rows: list[tuple[dict[str, Any], str, str, bool]] = []
    if fetch_targets:
        fetched_rows = list(
            await asyncio.gather(*[_one(s) for s in fetch_targets])
        )
    by_parent = {
        str(s.get("parent_id") or ""): (md, url, fetched)
        for s, md, url, fetched in fetched_rows
    }

    for seed in selected:
        parent = str(seed.get("parent_id") or "")
        if parent in by_parent:
            md, url, fetched = by_parent[parent]
            seed = {**seed, "url": url or seed.get("url") or ""}
        else:
            md, url, fetched = _synthetic_markdown(seed), "", False
        roots.append(root_document_from_seed(seed, md, url=url, fetched=fetched))

        if not fetched or len(queries) >= cap:
            continue
        # Enrich with page NLP only when the URL actually opened.
        chunks = paragraph_chunks(md)
        analyze_text = "\n\n".join(chunks[:6]) if chunks else md
        signals = _nlp_signals_from_text(analyze_text)
        already = sum(
            1
            for q in queries
            if str(q.get("root_parent_id") or "") == parent
        )
        room = max(0, nlp.max_queries_per_seed - already)
        per_seed = min(room, cap - len(queries))
        if per_seed <= 0:
            continue
        forged = queries_from_signals(
            seed,
            signals,
            forge_cfg=cfg,
            max_queries=per_seed + already,
            settings=settings,
        )
        # Skip title_snippet duplicates already emitted in the fast path.
        forged = [r for r in forged if r.get("forge_kind") != "title_snippet"]
        _absorb_queries(forged, queries=queries, seen_q=seen_q, cap=cap)

    queries.sort(key=lambda q: float(q.get("priority") or 0), reverse=True)
    LOGGER.info(
        "nlp forge seeds_in=%s selected=%s with_url=%s queries=%s roots=%s",
        len(seeds),
        len(selected),
        len(fetch_targets),
        len(queries),
        len(roots),
    )
    return queries[:cap], roots
