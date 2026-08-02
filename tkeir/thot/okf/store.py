"""Title: OKF bundle filesystem store (list / get / delete, tenant-scoped).

Demo layout (MinIO-ready)::

    workspace/users/<space>/okf/<bundle_id>/

When ``OKF_ROOT`` is set or an explicit ``root=`` is passed, the store also
supports the legacy flat ``{root}/<bundle_id>/`` layout (tests / migration).

Example:
    >>> from thot.okf.store import OkfBundleStore
    >>> OkfBundleStore  # doctest: +ELLIPSIS
    <class 'thot.okf.store.OkfBundleStore'>

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from thot.okf.exporter import (
    default_okf_root,
    delete_bundle,
    user_okf_root,
)
from thot.okf.models import OkfBundle
from thot.tools.search.vespa_client import normalize_user_space


class OkfBundleStore:
    """Read/list/delete per-user OKF bundles under the workspace tree."""

    def __init__(self, root: Path | str | None = None) -> None:
        # Explicit root → legacy flat layout (unit tests / migration tools).
        self.flat_root: Path | None = (
            Path(root).expanduser().resolve() if root is not None else None
        )
        if self.flat_root is not None:
            self.flat_root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        """Compatibility: flat root when set, else default legacy OKF_ROOT path."""
        if self.flat_root is not None:
            return self.flat_root
        return default_okf_root()

    def _legacy_flat_root(self) -> Path | None:
        if self.flat_root is not None:
            return self.flat_root
        if os.getenv("OKF_ROOT", "").strip():
            return default_okf_root()
        # Soft-read fallback for older demo bundles still under .tkeir-okf
        for candidate in (
            default_okf_root(),
            Path.cwd().resolve() / ".tkeir-okf",
            Path.cwd().resolve().parent / ".tkeir-okf",
        ):
            if candidate.is_dir():
                return candidate.resolve()
        return None

    def _user_okf_dir(self, user_space: str) -> Path:
        if self.flat_root is not None:
            return self.flat_root
        return user_okf_root(user_space)

    def _candidate_dirs(self, user_space: str, bundle_id: str) -> list[Path]:
        bid = (bundle_id or "").strip()
        if not bid:
            return []
        out: list[Path] = []
        primary = self._user_okf_dir(user_space) / bid
        out.append(primary)
        legacy = self._legacy_flat_root()
        if legacy is not None:
            flat = legacy / bid
            if flat not in out:
                out.append(flat)
        return out

    def _meta_path(self, bundle_dir: Path) -> Path:
        return bundle_dir / ".tkeir-meta.json"

    def _load_bundle(self, bundle_dir: Path) -> OkfBundle | None:
        meta = self._meta_path(bundle_dir)
        resolved = str(bundle_dir.resolve())
        if meta.is_file():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                raw = data.get("bundle") if isinstance(data, dict) else None
                if isinstance(raw, dict):
                    # Meta may still point at a previous OKF_ROOT. Bind to disk.
                    return OkfBundle.model_validate({**raw, "path": resolved})
            except (json.JSONDecodeError, ValueError):
                return None
        # Fallback: synthesize from directory
        if not (bundle_dir / "index.md").is_file():
            return None
        return OkfBundle(
            bundle_id=bundle_dir.name,
            user_space="unknown",
            concept_count=len(list(bundle_dir.rglob("*.md"))),
            path=resolved,
        )

    def list_bundles(self, user_space: str) -> list[OkfBundle]:
        """List bundles owned by ``user_space``."""
        space = normalize_user_space(user_space)
        seen: set[str] = set()
        out: list[OkfBundle] = []
        search_roots: list[Path] = [self._user_okf_dir(space)]
        legacy = self._legacy_flat_root()
        if legacy is not None and legacy not in search_roots:
            search_roots.append(legacy)
        for root in search_roots:
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                if not child.is_dir() or child.name in seen:
                    continue
                bundle = self._load_bundle(child)
                if bundle is None:
                    continue
                if normalize_user_space(bundle.user_space) != space:
                    continue
                seen.add(child.name)
                out.append(bundle)
        return out

    def get_bundle(self, bundle_id: str, user_space: str) -> OkfBundle | None:
        """Return bundle metadata when tenant matches (or path is under tenant OKF)."""
        space = normalize_user_space(user_space)
        user_root = self._user_okf_dir(space).resolve()
        for path in self._candidate_dirs(space, bundle_id):
            if not path.is_dir():
                continue
            bundle = self._load_bundle(path)
            if bundle is None:
                continue
            resolved = path.resolve()
            try:
                resolved.relative_to(user_root)
                owned_by_path = True
            except ValueError:
                owned_by_path = False
            if owned_by_path and self.flat_root is None:
                if normalize_user_space(bundle.user_space) != space:
                    return bundle.model_copy(update={"user_space": space})
                return bundle
            if normalize_user_space(bundle.user_space) != space:
                continue
            return bundle
        return None

    def get_index(self, bundle_id: str, user_space: str) -> str | None:
        bundle = self.get_bundle(bundle_id, user_space)
        if bundle is None:
            return None
        index = Path(bundle.path) / "index.md"
        if not index.is_file():
            return None
        return index.read_text(encoding="utf-8")

    def get_concept(
        self, bundle_id: str, concept_id: str, user_space: str
    ) -> str | None:
        bundle = self.get_bundle(bundle_id, user_space)
        if bundle is None:
            return None
        root = Path(bundle.path)
        rel = concept_id[:-3] if concept_id.endswith(".md") else concept_id
        path = root / f"{rel}.md"
        if not path.is_file():
            path = root / "concepts" / f"{Path(rel).name}.md"
        if not path.is_file():
            return None
        # Prevent path escape
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            return None
        return path.read_text(encoding="utf-8")

    def list_concepts(self, bundle_id: str, user_space: str) -> list[str]:
        bundle = self.get_bundle(bundle_id, user_space)
        if bundle is None:
            return []
        meta = self._meta_path(Path(bundle.path))
        if meta.is_file():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                ids = data.get("concept_ids")
                if isinstance(ids, list):
                    return [str(x) for x in ids]
            except json.JSONDecodeError:
                pass
        root = Path(bundle.path)
        return sorted(
            str(p.relative_to(root).with_suffix(""))
            for p in root.rglob("*.md")
            if p.name not in {"index.md", "log.md"}
        )

    def get_wiki(self, bundle_id: str, user_space: str) -> str | None:
        """Return ``wiki.md`` content when present."""
        return self.get_concept(bundle_id, "wiki", user_space)

    def put_wiki(self, bundle_id: str, user_space: str, markdown: str) -> str:
        """Overwrite ``wiki.md`` for a tenant-owned bundle. Returns absolute path."""
        bundle = self.get_bundle(bundle_id, user_space)
        if bundle is None:
            raise FileNotFoundError("bundle not found")
        text = (markdown or "").strip()
        if not text:
            raise ValueError("wiki markdown must not be empty")
        root = Path(bundle.path).resolve()
        wiki_path = (root / "wiki.md").resolve()
        try:
            wiki_path.relative_to(root)
        except ValueError as exc:
            raise ValueError("invalid wiki path") from exc
        wiki_path.parent.mkdir(parents=True, exist_ok=True)
        wiki_path.write_text(
            text if text.endswith("\n") else text + "\n", encoding="utf-8"
        )
        index_path = root / "index.md"
        if index_path.is_file():
            index_text = index_path.read_text(encoding="utf-8")
            if "wiki.md" not in index_text:
                index_path.write_text(
                    index_text.rstrip()
                    + "\n\n## LLMWiki\n\n- [wiki](wiki.md) — generated knowledge page\n",
                    encoding="utf-8",
                )
        return str(wiki_path)

    def delete(self, bundle_id: str, user_space: str) -> bool:
        bundle = self.get_bundle(bundle_id, user_space)
        if bundle is None:
            return False
        delete_bundle(Path(bundle.path))
        return True

    def bundle_payload(
        self, bundle_id: str, user_space: str, *, concept_id: str | None = None
    ) -> dict[str, Any] | None:
        """Payload for MCP ``okf_bundle_get``."""
        bundle = self.get_bundle(bundle_id, user_space)
        if bundle is None:
            return None
        if concept_id:
            text = self.get_concept(bundle_id, concept_id, user_space)
            if text is None:
                return {
                    "user_space": normalize_user_space(user_space),
                    "bundle_id": bundle_id,
                    "error": f"concept not found: {concept_id}",
                }
            return {
                "user_space": normalize_user_space(user_space),
                "bundle_id": bundle_id,
                "concept_id": concept_id,
                "markdown": text,
            }
        wiki_md = self.get_wiki(bundle_id, user_space)
        return {
            "user_space": normalize_user_space(user_space),
            "bundle_id": bundle_id,
            "bundle": bundle.model_dump(mode="json"),
            "index_md": self.get_index(bundle_id, user_space) or "",
            "concepts": self.list_concepts(bundle_id, user_space),
            "wiki_md": wiki_md or "",
            "has_wiki": bool(wiki_md and wiki_md.strip()),
        }


def migrate_flat_okf_into_workspace(
    flat_root: Path | str | None = None,
    *,
    workspace: Path | str | None = None,
) -> list[str]:
    """Move legacy flat ``OKF_ROOT/<id>`` bundles into ``users/<space>/okf/<id>``.

    Returns list of migrated bundle ids. Skips when destination already exists.
    """
    from thot.tools.ingest.user_workspace import UserWorkspace

    src_root = (
        Path(flat_root).expanduser().resolve()
        if flat_root is not None
        else default_okf_root()
    )
    if not src_root.is_dir():
        return []
    migrated: list[str] = []
    for child in sorted(src_root.iterdir()):
        if not child.is_dir():
            continue
        meta = child / ".tkeir-meta.json"
        space = "unknown"
        if meta.is_file():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                raw = data.get("bundle") if isinstance(data, dict) else None
                if isinstance(raw, dict) and raw.get("user_space"):
                    space = str(raw["user_space"])
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        dest_parent = UserWorkspace(space, root=workspace).ensure_okf_layout()
        dest = dest_parent / child.name
        if dest.exists():
            continue
        # Rewrite meta path before move
        if meta.is_file():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                if isinstance(data.get("bundle"), dict):
                    data["bundle"]["path"] = str(dest.resolve())
                    meta.write_text(
                        json.dumps(data, indent=2) + "\n", encoding="utf-8"
                    )
            except (json.JSONDecodeError, TypeError, ValueError, OSError):
                pass
        shutil.move(str(child), str(dest))
        migrated.append(child.name)
    return migrated
