"""Title: Unit tests for OKF MCP tools (tenant isolation).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from thot.mcp.authz import McpPrincipal
from thot.mcp.handlers import McpHandlers
from thot.mcp.tools_catalog import list_tool_names
from thot.okf.exporter import render_frontmatter
from thot.okf.models import OkfBundle, OkfConceptFrontmatter
from thot.okf.store import OkfBundleStore


class RecordingBackend:
    def __init__(self) -> None:
        self.spaces: list[str] = []

    async def hybrid_search(self, query, *, hits, user_space, language=None):
        self.spaces.append(user_space)
        return {"user_space": user_space, "chunks": []}

    async def rag_query(self, query, **kw):
        return await self.hybrid_search(
            query, hits=kw.get("hits", 8), user_space=kw["user_space"]
        )

    async def get_document(self, **kw):
        self.spaces.append(kw["user_space"])
        return {"user_space": kw["user_space"], "fields": {}}

    async def ontology_from_query(self, query, **kw):
        self.spaces.append(kw["user_space"])
        return {"user_space": kw["user_space"], "summary": ""}

    async def okf_bundle_list(self, *, user_space):
        self.spaces.append(user_space)
        return {"user_space": user_space, "bundles": []}

    async def okf_bundle_get(self, *, user_space, bundle_id, concept_id=None):
        self.spaces.append(user_space)
        return {
            "user_space": user_space,
            "bundle_id": bundle_id,
            "concept_id": concept_id,
            "markdown": "# hi",
        }


def test_catalog_includes_okf_tools():
    names = list_tool_names()
    assert "okf_bundle_list" in names
    assert "okf_bundle_get" in names


def test_handlers_ignore_user_space_override():
    backend = RecordingBackend()
    h = McpHandlers(backend=backend)
    out = asyncio.run(
        h.invoke(
            "okf_bundle_list",
            {"user_space": "attacker"},
            McpPrincipal(user_space="alice"),
        )
    )
    assert out["user_space"] == "alice"
    assert backend.spaces == ["alice"]
    out2 = asyncio.run(
        h.invoke(
            "okf_bundle_get",
            {"bundle_id": "b1", "user_space": "attacker"},
            McpPrincipal(user_space="alice"),
        )
    )
    assert out2["user_space"] == "alice"
    assert out2["bundle_id"] == "b1"


def test_store_tenant_isolation(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OKF_ROOT", str(tmp_path))
    store = OkfBundleStore(tmp_path)
    bundle_dir = tmp_path / "bundle-a"
    bundle_dir.mkdir()
    (bundle_dir / "index.md").write_text("# Index\n", encoding="utf-8")
    fm = OkfConceptFrontmatter(
        type="Document",
        tkeir_doc_id="d1",
        tkeir_user_space="alice",
    )
    (bundle_dir / "concepts").mkdir()
    (bundle_dir / "concepts" / "d1.md").write_text(
        render_frontmatter(fm) + "\n# Body\n", encoding="utf-8"
    )
    meta = {
        "bundle": (
            OkfBundle(
                bundle_id="bundle-a",
                user_space="alice",
                concept_count=1,
                path=str(bundle_dir),
            ).model_dump(mode="json")
        ),
        "concept_ids": ["concepts/d1"],
    }
    (bundle_dir / ".tkeir-meta.json").write_text(
        json.dumps(meta), encoding="utf-8"
    )
    assert store.list_bundles("alice")
    assert store.list_bundles("bob") == []
    assert store.get_bundle("bundle-a", "bob") is None
    payload = store.bundle_payload(
        "bundle-a", "alice", concept_id="concepts/d1"
    )
    assert payload is not None
    assert "Body" in payload["markdown"]
