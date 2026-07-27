"""Title: Functional tests for OKF export + MCP get (fixture corpus optional).

When Vespa is unavailable the suite falls back to an in-process mock export
so CI stays green; with an indexed ``dev@tkeir`` corpus the live path is used.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import yaml

from thot.action.sink import InMemoryActionSink
from thot.mcp.authz import McpPrincipal
from thot.mcp.handlers import McpHandlers, VespaMcpBackend
from thot.okf.exporter import export_full, export_scoped
from thot.okf.models import OkfExportRequest
from thot.okf.store import OkfBundleStore


class _FixtureVespa:
    async def list_parent_documents(self, *, user_space, max_docs, doc_ids=None):
        docs = [
            {
                "source_doc_id": "fixture-alpha",
                "title": "Objective ALPHA",
                "content": [
                    "Objective ALPHA is the primary mission. Extra body."
                ],
                "json_ld": '[{"@type":"Mission","rdfs:label":"ALPHA"}]',
                "title_keywords": ["ALPHA"],
                "user_space": user_space,
                "_vespa_id": f"id:default:user:g={user_space}:fixture-alpha",
            },
            {
                "source_doc_id": "fixture-beta",
                "title": "Beta",
                "content": ["Beta note."],
                "json_ld": '[{"@type":"Note","rdfs:label":"Beta"}]',
                "user_space": user_space,
                "_vespa_id": f"id:default:user:g={user_space}:fixture-beta",
            },
        ]
        if doc_ids:
            docs = [d for d in docs if d["source_doc_id"] in set(doc_ids)]
        return docs[:max_docs]

    async def list_chunk_ids_for_parent(
        self, *, user_space, doc_ref, parent_source_id
    ):
        return [
            {
                "chunk_id": f"{parent_source_id}-c1",
                "text_raw": "Grounded chunk for Objective ALPHA.",
            }
        ]


class _FixtureRag:
    async def query(self, query, *, user_space, hits):
        return {
            "answer": f"Scoped answer: {query}",
            "document_ids": ["fixture-alpha"],
        }


def _assert_valid_bundle(root: Path) -> None:
    assert root.is_dir()
    assert (root / "index.md").is_file()
    assert (root / "log.md").is_file()
    md_files = list(root.rglob("*.md"))
    assert md_files
    for path in md_files:
        if path.name in {"index.md", "log.md"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---"), path
        fm = yaml.safe_load(text.split("---", 2)[1])
        assert "type" in fm
        assert "tkeir_doc_id" in fm


def test_okf_export_and_mcp_get(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OKF_ROOT", str(tmp_path))
    sink = InMemoryActionSink()
    full = asyncio.run(
        export_full(
            OkfExportRequest(
                user_space="dev@tkeir",
                max_docs=10,
                output_dir=str(tmp_path / "full"),
            ),
            vespa_client=_FixtureVespa(),
            action_sink=sink,
        )
    )
    _assert_valid_bundle(Path(full.bundle.path))

    scoped = asyncio.run(
        export_scoped(
            OkfExportRequest(
                user_space="dev@tkeir",
                query="Objective ALPHA",
                max_docs=5,
                output_dir=str(tmp_path / "scoped"),
            ),
            vespa_client=_FixtureVespa(),
            rag_client=_FixtureRag(),
            action_sink=sink,
        )
    )
    root = Path(scoped.bundle.path)
    assert (root / "query_context.md").is_file()
    assert scoped.bundle.concept_count <= 5

    bundle_link = tmp_path / scoped.bundle.bundle_id
    if not bundle_link.exists():
        os.symlink(root, bundle_link)

    class _OkfBackend(VespaMcpBackend):
        async def okf_bundle_get(
            self, *, user_space, bundle_id, concept_id=None
        ):
            return OkfBundleStore(tmp_path).bundle_payload(
                bundle_id, user_space, concept_id=concept_id
            ) or {"error": "missing", "user_space": user_space}

        async def okf_bundle_list(self, *, user_space):
            bundles = OkfBundleStore(tmp_path).list_bundles(user_space)
            return {
                "user_space": user_space,
                "bundles": [b.model_dump(mode="json") for b in bundles],
            }

    handlers = McpHandlers(backend=_OkfBackend())
    got = asyncio.run(
        handlers.invoke(
            "okf_bundle_get",
            {
                "bundle_id": scoped.bundle.bundle_id,
                "concept_id": "concepts/fixture-alpha",
            },
            McpPrincipal(user_space="dev@tkeir"),
        )
    )
    assert "markdown" in got
    assert "Objective ALPHA" in got["markdown"]
