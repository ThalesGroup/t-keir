"""Title: OKF bundle filesystem store (list / get / delete, tenant-scoped).

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
from pathlib import Path
from typing import Any

from thot.okf.exporter import default_okf_root, delete_bundle
from thot.okf.models import OkfBundle
from thot.tools.search.vespa_client import normalize_user_space


class OkfBundleStore:
    """Read/list/delete bundles under ``OKF_ROOT``."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root else default_okf_root()
        self.root.mkdir(parents=True, exist_ok=True)

    def _meta_path(self, bundle_dir: Path) -> Path:
        return bundle_dir / ".tkeir-meta.json"

    def _load_bundle(self, bundle_dir: Path) -> OkfBundle | None:
        meta = self._meta_path(bundle_dir)
        if meta.is_file():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                raw = data.get("bundle") if isinstance(data, dict) else None
                if isinstance(raw, dict):
                    return OkfBundle.model_validate(raw)
            except (json.JSONDecodeError, ValueError):
                return None
        # Fallback: synthesize from directory
        if not (bundle_dir / "index.md").is_file():
            return None
        return OkfBundle(
            bundle_id=bundle_dir.name,
            user_space="unknown",
            concept_count=len(list(bundle_dir.rglob("*.md"))),
            path=str(bundle_dir.resolve()),
        )

    def list_bundles(self, user_space: str) -> list[OkfBundle]:
        """List bundles owned by ``user_space``."""
        space = normalize_user_space(user_space)
        out: list[OkfBundle] = []
        if not self.root.is_dir():
            return out
        for child in sorted(self.root.iterdir()):
            if not child.is_dir():
                continue
            bundle = self._load_bundle(child)
            if bundle is None:
                continue
            if normalize_user_space(bundle.user_space) != space:
                continue
            out.append(bundle)
        return out

    def get_bundle(self, bundle_id: str, user_space: str) -> OkfBundle | None:
        """Return bundle metadata when tenant matches."""
        space = normalize_user_space(user_space)
        path = self.root / bundle_id
        if not path.is_dir():
            # Also allow absolute path lookups by id under root only
            return None
        bundle = self._load_bundle(path)
        if bundle is None:
            return None
        if normalize_user_space(bundle.user_space) != space:
            return None
        return bundle

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
        return {
            "user_space": normalize_user_space(user_space),
            "bundle_id": bundle_id,
            "bundle": bundle.model_dump(mode="json"),
            "index_md": self.get_index(bundle_id, user_space) or "",
            "concepts": self.list_concepts(bundle_id, user_space),
        }
