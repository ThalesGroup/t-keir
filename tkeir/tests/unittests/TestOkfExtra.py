"""Title: Extra OKF coverage — CLI, tar, store edges, applicator fallbacks.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from thot.agent.models import GroundedFinding, GroundedFindings
from thot.okf.applicator import enrichments_from_grounded
from thot.okf.exporter import (
    VespaOkfBackend,
    cli_main,
    delete_bundle,
    first_sentence,
    tar_bundle,
)
from thot.okf.models import OkfBundle
from thot.okf.store import OkfBundleStore


def test_first_sentence_fallback_and_empty():
    assert first_sentence("") == ""
    assert "Hello" in first_sentence("Hello? World!")


def test_tar_and_delete(tmp_path: Path):
    root = tmp_path / "b1"
    root.mkdir()
    (root / "index.md").write_text("# i\n", encoding="utf-8")
    archive = tar_bundle(root)
    assert archive.is_file()
    assert archive.name.endswith(".tar.gz")
    delete_bundle(root)
    assert not root.exists()


def test_cli_main_scoped(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("OKF_ROOT", str(tmp_path))

    async def fake_scoped(request, **kw):
        from thot.okf.models import OkfExportResult

        path = tmp_path / "out"
        path.mkdir(exist_ok=True)
        return OkfExportResult(
            bundle=OkfBundle(
                bundle_id="x",
                user_space=request.user_space,
                query=request.query,
                concept_count=0,
                path=str(path),
            ),
            action_record_id="a",
        )

    with patch("thot.okf.exporter.export_scoped", new=fake_scoped):
        code = cli_main(
            ["--user-space", "dev@tkeir", "--query", "q", "--max-docs", "3"]
        )
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["bundle_id"] == "x"
    assert out["query"] == "q"


def test_cli_main_full(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("OKF_ROOT", str(tmp_path))

    async def fake_full(request, **kw):
        from thot.okf.models import OkfExportResult

        path = tmp_path / "full"
        path.mkdir(exist_ok=True)
        return OkfExportResult(
            bundle=OkfBundle(
                bundle_id="y",
                user_space=request.user_space,
                concept_count=1,
                path=str(path),
            ),
            action_record_id="b",
        )

    with patch("thot.okf.exporter.export_full", new=fake_full):
        code = cli_main(["--user-space", "dev@tkeir", "--output", str(tmp_path / "full")])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["bundle_id"] == "y"


def test_enrichments_fallback_from_findings():
    result = GroundedFindings(
        findings=[
            GroundedFinding(
                claim="Claim text",
                chunk_ids=["c1"],
                document_ids=["okf:concepts/doc-1"],
            )
        ],
        notes="not-json",
    )
    enrichment = enrichments_from_grounded(result)
    assert enrichment.findings[0].concept_id == "concepts/doc-1"
    assert enrichment.findings[0].enrichments.description == "Claim text"


def test_store_missing_and_fallback(tmp_path: Path):
    store = OkfBundleStore(tmp_path)
    assert store.list_bundles("dev@tkeir") == []
    assert store.get_bundle("missing", "dev@tkeir") is None
    # Directory with index but no meta
    d = tmp_path / "orphan"
    d.mkdir()
    (d / "index.md").write_text("# i\n", encoding="utf-8")
    (d / "concepts").mkdir()
    (d / "concepts" / "a.md").write_text(
        "---\ntype: Document\n---\n", encoding="utf-8"
    )
    bundle = store._load_bundle(d)
    assert bundle is not None
    assert bundle.bundle_id == "orphan"


def test_document_ids_from_rag_variants():
    from thot.okf.exporter import _document_ids_from_rag

    ids = _document_ids_from_rag(
        {
            "documents": [{"source_doc_id": "a"}, {"id": "b"}],
            "chunks": [{"parent_doc_id": "c"}, {"document_id": "a"}],
        },
        max_docs=10,
    )
    assert ids[:3] == ["a", "b", "c"]


def test_http_rag_client_error(monkeypatch):
    import asyncio

    from thot.okf.exporter import HttpOkfRagClient

    class FakeResp:
        is_error = True
        text = "boom"

        def json(self):
            return {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(
        "httpx.AsyncClient", lambda **k: FakeClient()
    )
    out = asyncio.run(
        HttpOkfRagClient("http://example").query(
            "q", user_space="dev@tkeir", hits=3
        )
    )
    assert out["document_ids"] == []


def test_applicator_skips_ungrounded_and_missing(tmp_path: Path):
    from thot.okf.applicator import OkfEnrichmentApplicator
    from thot.okf.models import OkfEnrichment, OkfEnrichmentFinding

    summary = OkfEnrichmentApplicator(tmp_path).apply(
        OkfEnrichment(
            findings=[
                OkfEnrichmentFinding(
                    concept_id="missing",
                    claim="x",
                    chunk_ids=["c1"],
                ),
                OkfEnrichmentFinding(
                    concept_id="no-prov",
                    claim="y",
                ),
            ]
        )
    )
    assert summary["applied"] == 0
    assert "missing" in summary["missing"]
    assert "no-prov" in summary["missing"]


def test_store_concept_and_list(tmp_path: Path):
    from thot.okf.exporter import render_frontmatter
    from thot.okf.models import OkfConceptFrontmatter

    store = OkfBundleStore(tmp_path)
    bid = "b2"
    root = tmp_path / bid
    root.mkdir()
    (root / "index.md").write_text("# i\n", encoding="utf-8")
    (root / "concepts").mkdir()
    fm = OkfConceptFrontmatter(
        type="Document",
        tkeir_doc_id="d",
        tkeir_user_space="dev@tkeir",
    )
    (root / "concepts" / "d.md").write_text(
        render_frontmatter(fm) + "\nbody\n", encoding="utf-8"
    )
    meta = {
        "bundle": OkfBundle(
            bundle_id=bid,
            user_space="dev@tkeir",
            concept_count=1,
            path=str(root),
        ).model_dump(mode="json"),
        "concept_ids": ["concepts/d"],
    }
    (root / ".tkeir-meta.json").write_text(json.dumps(meta), encoding="utf-8")
    assert store.get_index(bid, "dev@tkeir")
    assert "body" in (store.get_concept(bid, "concepts/d", "dev@tkeir") or "")
    assert store.list_concepts(bid, "dev@tkeir") == ["concepts/d"]
    assert store.delete(bid, "dev@tkeir") is True


def test_vespa_okf_backend_list():
    import asyncio

    vespa = MagicMock()
    vespa.search = AsyncMock(
        return_value={
            "root": {
                "children": [
                    {
                        "id": "id:default:tkeir_document:g=dev@tkeir:k1",
                        "fields": {
                            "user_space": "dev@tkeir",
                            "source_doc_id": "doc-1",
                            "title": "T",
                        },
                    },
                    {
                        "id": "id:default:tkeir_document:g=other:k2",
                        "fields": {
                            "user_space": "other",
                            "source_doc_id": "doc-2",
                        },
                    },
                ]
            }
        }
    )
    backend = VespaOkfBackend(vespa=vespa)

    async def _run():
        docs = await backend.list_parent_documents(
            user_space="dev@tkeir", max_docs=10, doc_ids=["doc-1"]
        )
        assert len(docs) == 1
        assert docs[0]["source_doc_id"] == "doc-1"

        vespa.search = AsyncMock(
            return_value={
                "root": {
                    "children": [
                        {
                            "fields": {
                                "user_space": "dev@tkeir",
                                "chunk_id": "c1",
                                "doc_ref": (
                                    "id:default:tkeir_document:g=dev@tkeir:k1"
                                ),
                                "text_raw": "hello world",
                            }
                        }
                    ]
                }
            }
        )
        chunks = await backend.list_chunk_ids_for_parent(
            user_space="dev@tkeir",
            doc_ref="id:default:tkeir_document:g=dev@tkeir:k1",
            parent_source_id="doc-1",
        )
        assert chunks[0]["chunk_id"] == "c1"

    asyncio.run(_run())
