"""Title: Unit tests for OKF exporter (mock Vespa / RAG).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from thot.action.sink import InMemoryActionSink
from thot.okf.exporter import (
    export_full,
    export_scoped,
    first_sentence,
    render_frontmatter,
)
from thot.okf.models import OkfConceptFrontmatter, OkfExportRequest


class FakeVespa:
    def __init__(self) -> None:
        self.listed = 0

    async def list_parent_documents(
        self, *, user_space, max_docs, doc_ids=None
    ):
        self.listed += 1
        docs = [
            {
                "source_doc_id": "doc-alpha",
                "title": "Objective ALPHA",
                "content": [
                    "Objective ALPHA is the primary mission. More detail follows."
                ],
                "json_ld": (
                    '[{"@type":"Organization","rdfs:label":"ALPHA","frequency":2}]'
                ),
                "title_keywords": ["ALPHA", "mission"],
                "user_space": user_space,
                "_vespa_id": f"id:default:user:g={user_space}:doc-alpha",
            },
            {
                "source_doc_id": "doc-beta",
                "title": "Beta note",
                "content": ["Beta has no ontology yet."],
                "json_ld": "",
                "user_space": user_space,
                "_vespa_id": f"id:default:user:g={user_space}:doc-beta",
            },
        ]
        if doc_ids:
            wanted = set(doc_ids)
            docs = [d for d in docs if d["source_doc_id"] in wanted]
        return docs[:max_docs]

    async def list_chunk_ids_for_parent(
        self, *, user_space, doc_ref, parent_source_id
    ):
        return [
            {
                "chunk_id": f"{parent_source_id}-c1",
                "text_raw": "Chunk excerpt about the topic.",
            }
        ]


class FakeRag:
    async def query(self, query, *, user_space, hits):
        return {
            "answer": f"Answer for {query}",
            "document_ids": ["doc-alpha"],
            "chunks": [
                {
                    "chunk_id": "doc-alpha-c1",
                    "parent_doc_id": "doc-alpha",
                    "text_raw": "x",
                }
            ],
        }


def test_first_sentence():
    assert first_sentence("Hello world. More.") == "Hello world."


def test_export_full(tmp_path: Path):
    sink = InMemoryActionSink()
    out = tmp_path / "bundle"
    result = asyncio.run(
        export_full(
            OkfExportRequest(
                user_space="dev@tkeir", max_docs=10, output_dir=str(out)
            ),
            vespa_client=FakeVespa(),
            action_sink=sink,
        )
    )
    assert result.bundle.concept_count == 2
    assert (out / "index.md").is_file()
    assert (out / "log.md").is_file()
    concept = out / "concepts" / "doc-alpha.md"
    assert concept.is_file()
    text = concept.read_text(encoding="utf-8")
    assert text.startswith("---")
    fm_raw = text.split("---", 2)[1]
    fm = yaml.safe_load(fm_raw)
    assert fm["type"] == "Document"
    assert fm["tkeir_doc_id"] == "doc-alpha"
    assert fm["tkeir_user_space"] == "dev@tkeir"
    assert "tkeir_okf_version" in fm
    # description is first sentence only
    assert "More detail" not in (fm.get("description") or "")
    assert (out / "chunks" / "doc-alpha-c1.md").is_file()
    assert "doc-beta" in result.unfilled_docs
    assert len(sink) >= 1


def test_export_scoped(tmp_path: Path):
    sink = InMemoryActionSink()
    out = tmp_path / "scoped"
    result = asyncio.run(
        export_scoped(
            OkfExportRequest(
                user_space="dev@tkeir",
                query="Objective ALPHA",
                max_docs=5,
                output_dir=str(out),
            ),
            vespa_client=FakeVespa(),
            rag_client=FakeRag(),
            action_sink=sink,
        )
    )
    assert result.bundle.query == "Objective ALPHA"
    assert (out / "query_context.md").is_file()
    assert (out / "wiki.md").is_file()
    wiki = (out / "wiki.md").read_text(encoding="utf-8")
    assert "type: Wiki" in wiki
    assert "Objective ALPHA" in wiki
    assert "## Answer" in wiki
    assert result.bundle.concept_count <= 5
    qc = (out / "query_context.md").read_text(encoding="utf-8")
    assert "Objective ALPHA" in qc


def test_render_frontmatter_contains_type():
    fm = OkfConceptFrontmatter(
        type="Chunk",
        tkeir_doc_id="d",
        tkeir_user_space="dev@tkeir",
    )
    text = render_frontmatter(fm)
    assert "type: Chunk" in text
