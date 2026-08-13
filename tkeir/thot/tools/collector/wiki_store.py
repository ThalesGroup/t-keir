"""Title: Persist dated wiki panel bundles under the collector workspace.

Saves everything the Osiris wiki panel needs to restore: live wiki markdown
(Answer / Timeline / Sources), ontology + BO coverage, queries, documents,
ranked chunks, and sources — stamped with a UTC date id.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

BUNDLE_VERSION = 1
_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def wiki_store_dir(workspace: Path) -> Path:
    """Return ``workspace/collector/wikis`` (created if missing)."""
    path = Path(workspace) / "collector" / "wikis"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_wiki_bundle(
    *,
    wiki_snapshot: dict[str, Any],
    queries: list[dict[str, Any]] | None = None,
    documents: list[dict[str, Any]] | None = None,
    ranked_chunks: list[dict[str, Any]] | None = None,
    topic: str | None = None,
    meta: dict[str, Any] | None = None,
    saved_at: str | None = None,
    bundle_id: str | None = None,
) -> dict[str, Any]:
    """Assemble a panel-restorable wiki bundle."""
    stamp = bundle_id or _now_stamp()
    when = saved_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snap = dict(wiki_snapshot or {})
    # Runtime-only flags — not useful on disk.
    snap.pop("producing", None)
    snap.pop("queued", None)
    q = list(queries or [])
    docs = list(documents or [])
    return {
        "version": BUNDLE_VERSION,
        "id": stamp,
        "saved_at": when,
        "topic": (topic or "osiris-live").strip() or "osiris-live",
        "wiki": snap,
        "queries": q,
        "documents": docs,
        "ranked_chunks": list(ranked_chunks or []),
        "meta": {
            "queryCount": len(q),
            "documentCount": len(docs),
            "ranked_count": snap.get("ranked_count"),
            "chunk_count": snap.get("chunk_count"),
            "iteration": snap.get("iteration"),
            "backend": snap.get("backend"),
            **(meta or {}),
        },
    }


def save_wiki_bundle(
    workspace: Path,
    bundle: dict[str, Any],
    *,
    enabled: bool = True,
) -> Path | None:
    """Write ``wikis/<id>.json`` (+ ``.md``) and refresh ``latest.json``.

    Returns the JSON path, or ``None`` when disabled / empty wiki.
    """
    if not enabled:
        return None
    wiki = bundle.get("wiki") or {}
    markdown = str(wiki.get("markdown") or "").strip()
    if not markdown:
        LOGGER.info("skip wiki save — empty markdown")
        return None

    out_dir = wiki_store_dir(workspace)
    raw_id = str(bundle.get("id") or _now_stamp())
    safe_id = _SAFE_ID.sub("_", raw_id).strip("._") or _now_stamp()
    bundle = {**bundle, "id": safe_id}

    json_path = out_dir / f"{safe_id}.json"
    md_path = out_dir / f"{safe_id}.md"
    latest_path = out_dir / "latest.json"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(bundle, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    header = [
        f"<!-- tkeir wiki bundle {safe_id} · {bundle.get('saved_at')} -->",
        f"<!-- topic: {bundle.get('topic')} -->",
        "",
    ]
    md_path.write_text("\n".join(header) + markdown + "\n", encoding="utf-8")

    with latest_path.open("w", encoding="utf-8") as handle:
        json.dump(bundle, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    LOGGER.info(
        "saved wiki bundle id=%s queries=%s docs=%s → %s",
        safe_id,
        len(bundle.get("queries") or []),
        len(bundle.get("documents") or []),
        json_path,
    )
    return json_path


def list_wiki_bundles(
    workspace: Path,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List saved bundles newest-first (summary rows, not full payloads)."""
    out_dir = wiki_store_dir(workspace)
    rows: list[dict[str, Any]] = []
    for path in sorted(out_dir.glob("*.json"), reverse=True):
        if path.name == "latest.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("skip unreadable wiki bundle %s: %s", path, exc)
            continue
        wiki = data.get("wiki") or {}
        meta = data.get("meta") or {}
        rows.append(
            {
                "id": data.get("id") or path.stem,
                "saved_at": data.get("saved_at"),
                "topic": data.get("topic"),
                "path": str(path),
                "iteration": wiki.get("iteration") or meta.get("iteration"),
                "queryCount": meta.get("queryCount", len(data.get("queries") or [])),
                "documentCount": meta.get(
                    "documentCount", len(data.get("documents") or [])
                ),
                "markdown_chars": len(str(wiki.get("markdown") or "")),
                "backend": wiki.get("backend") or meta.get("backend"),
                "has_ontology": bool(wiki.get("ontology")),
                "has_timeline": "## Timeline" in str(wiki.get("markdown") or ""),
            }
        )
        if len(rows) >= max(1, int(limit)):
            break
    return rows


def load_wiki_bundle(
    workspace: Path,
    bundle_id: str | None = None,
) -> dict[str, Any] | None:
    """Load a bundle by id, or the latest when ``bundle_id`` is None/``latest``."""
    out_dir = wiki_store_dir(workspace)
    if not bundle_id or bundle_id.strip().lower() in {"latest", "last", ""}:
        latest = out_dir / "latest.json"
        if latest.is_file():
            try:
                return json.loads(latest.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("latest.json unreadable: %s", exc)
        listed = list_wiki_bundles(workspace, limit=1)
        if not listed:
            return None
        bundle_id = str(listed[0]["id"])

    safe = _SAFE_ID.sub("_", str(bundle_id)).strip("._")
    path = out_dir / f"{safe}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("wiki bundle load failed %s: %s", path, exc)
        return None
