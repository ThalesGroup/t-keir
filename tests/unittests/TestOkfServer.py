"""Title: Unit tests for OKF HTTP server routes.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from thot.okf.exporter import render_frontmatter
from thot.okf.models import OkfBundle, OkfConceptFrontmatter, OkfExportResult
from thot.okf.store import OkfBundleStore


@pytest.fixture
def okf_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OKF_ROOT", str(tmp_path))
    monkeypatch.setenv("GOVERNOR_MODE", "off")
    monkeypatch.setenv("GOVERNOR_STATE_ROOT", str(tmp_path / "gov"))
    monkeypatch.setenv("VESPA_USER_SPACE", "dev@tkeir")
    from thot.governor.config import governor_settings

    governor_settings.cache_clear()
    # Import app after governor mode is off so middleware is not wired.
    import importlib

    import thot.okf.server as okf_server

    importlib.reload(okf_server)
    with TestClient(okf_server.app) as client:
        yield client, tmp_path, okf_server
    governor_settings.cache_clear()


def _seed_bundle(root: Path, *, space: str = "dev@tkeir") -> str:
    bundle_id = "bundle-test-1"
    bundle_dir = root / bundle_id
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "index.md").write_text("# Index\n", encoding="utf-8")
    (bundle_dir / "log.md").write_text("# Log\n", encoding="utf-8")
    (bundle_dir / "concepts").mkdir(exist_ok=True)
    fm = OkfConceptFrontmatter(
        type="Document",
        title="Alpha",
        tkeir_doc_id="doc-1",
        tkeir_user_space=space,
    )
    (bundle_dir / "concepts" / "doc-1.md").write_text(
        render_frontmatter(fm) + "\n# Alpha\n", encoding="utf-8"
    )
    meta = {
        "bundle": (
            OkfBundle(
                bundle_id=bundle_id,
                user_space=space,
                concept_count=1,
                path=str(bundle_dir),
            ).model_dump(mode="json")
        ),
        "concept_ids": ["concepts/doc-1"],
    }
    (bundle_dir / ".tkeir-meta.json").write_text(
        json.dumps(meta), encoding="utf-8"
    )
    return bundle_id


def test_health_ready(okf_client):
    client, _tmp, _mod = okf_client
    assert client.get("/health").json()["status"] == "ok"
    ready = client.get("/ready").json()
    assert ready["status"] == "ready"


def test_list_and_get_bundle(okf_client):
    client, tmp_path, _mod = okf_client
    bundle_id = _seed_bundle(tmp_path)
    listed = client.get("/okf/bundles").json()
    assert listed["user_space"] == "dev@tkeir"
    assert any(b["bundle_id"] == bundle_id for b in listed["bundles"])
    detail = client.get(f"/okf/bundles/{bundle_id}").json()
    assert detail["bundle_id"] == bundle_id
    assert "index_md" in detail


def test_download_and_metrics(okf_client):
    client, tmp_path, _mod = okf_client
    bundle_id = _seed_bundle(tmp_path)
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    dl = client.get(f"/okf/bundles/{bundle_id}/download")
    assert dl.status_code == 200
    assert "gzip" in (dl.headers.get("content-type") or "")


def test_scoped_export_http(okf_client):
    client, tmp_path, okf_server = okf_client
    fake = OkfExportResult(
        bundle=OkfBundle(
            bundle_id="scoped",
            user_space="dev@tkeir",
            query="q",
            concept_count=1,
            path=str(tmp_path / "scoped"),
        ),
        action_record_id="act2",
    )
    with patch.object(
        okf_server, "export_scoped", new=AsyncMock(return_value=fake)
    ):
        resp = client.post(
            "/okf/export", json={"query": "Objective ALPHA", "max_docs": 5}
        )
        assert resp.status_code == 200
        assert resp.json()["bundle"]["query"] == "q"


def test_missing_bundle_404(okf_client):
    client, _tmp, _mod = okf_client
    assert client.get("/okf/bundles/nope").status_code == 404
    assert client.delete("/okf/bundles/nope").status_code == 404


def test_put_wiki_editable(okf_client):
    client, tmp_path, _mod = okf_client
    bundle_id = _seed_bundle(tmp_path)
    markdown = "---\ntype: Wiki\ntitle: Edited\ntkeir_doc_id: wiki:edited\ntkeir_user_space: dev@tkeir\n---\n\n# Edited\n\nBody.\n"
    resp = client.put(
        f"/okf/bundles/{bundle_id}/wiki",
        json={"markdown": markdown},
    )
    assert resp.status_code == 200
    assert resp.json()["wiki_path"] == "wiki.md"
    detail = client.get(f"/okf/bundles/{bundle_id}").json()
    assert detail["has_wiki"] is True
    assert "Edited" in detail["wiki_md"]
    assert (tmp_path / bundle_id / "wiki.md").is_file()


def test_export_and_delete(okf_client):
    client, tmp_path, okf_server = okf_client
    fake = OkfExportResult(
        bundle=OkfBundle(
            bundle_id="exported",
            user_space="dev@tkeir",
            concept_count=0,
            path=str(tmp_path / "exported"),
        ),
        action_record_id="act",
    )
    (tmp_path / "exported").mkdir(exist_ok=True)
    (tmp_path / "exported" / "index.md").write_text("# i\n", encoding="utf-8")
    meta = {
        "bundle": fake.bundle.model_dump(mode="json"),
        "concept_ids": [],
    }
    (tmp_path / "exported" / ".tkeir-meta.json").write_text(
        json.dumps(meta), encoding="utf-8"
    )
    with patch.object(
        okf_server, "export_full", new=AsyncMock(return_value=fake)
    ):
        resp = client.post("/okf/export", json={"max_docs": 5})
        assert resp.status_code == 200
        assert resp.json()["bundle"]["bundle_id"] == "exported"
        _seed_bundle(tmp_path)
        deleted = client.delete("/okf/bundles/bundle-test-1")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True
        assert (
            OkfBundleStore(tmp_path).get_bundle("bundle-test-1", "dev@tkeir")
            is None
        )
