"""Title: Ingest

Unit tests for ingest manifest, store, worker, and API.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from thot.tools.ingest.config import ingest_settings
from thot.tools.ingest.fetch import doc_id_from_content, fetch_bytes
from thot.tools.ingest.manifest import (
    embedder_fingerprint,
    idempotency_key,
    pipeline_config_sha256,
)
from thot.tools.ingest.models import (
    EmbedderInfo,
    IngestJob,
    IngestJobStatus,
    IngestManifest,
    SourceInfo,
)
from thot.tools.ingest.store import IngestStore
from thot.tools.ingest.worker import IngestWorker


@pytest.fixture
def ingest_root(monkeypatch):
    ingest_settings.cache_clear()
    with tempfile.TemporaryDirectory() as temp_dir:
        monkeypatch.setenv("INGEST_ROOT", temp_dir)
        # Ingest API wires governor middleware at import-time; make the
        # ingest test harness independent from governor state initialization.
        monkeypatch.setenv("GOVERNOR_MODE", "off")
        monkeypatch.setenv(
            "GOVERNOR_STATE_ROOT", str(Path(temp_dir) / "governor")
        )
        from thot.governor.config import governor_settings

        governor_settings.cache_clear()
        monkeypatch.setenv("INGEST_AUTH_ENABLED", "false")
        monkeypatch.setenv("INGEST_INDEX_ENABLED", "false")
        ingest_settings.cache_clear()
        yield Path(temp_dir)
        ingest_settings.cache_clear()
        governor_settings.cache_clear()


def test_document_extras_from_metadata_promotes_nato_paths():
    from thot.tools.ingest.worker import document_extras_from_metadata

    # Server only stamps already-staged absolute paths (from uploaded bytes).
    extras = document_extras_from_metadata(
        {
            "corpus": "osint",
            "topic_id": "situational_awareness",
            # Client path strings in metadata must not leak into derive-from.
            "ontologies": ["/client/secret/path.ttl"],
        },
        ontologies=[
            "/var/tkeir/ingest/uploaded_ontologies/abc/c2sim_combined.ttl",
        ],
    )
    assert extras is not None
    assert extras["corpus"] == "osint"
    assert extras["ontologies"] == [
        "/var/tkeir/ingest/uploaded_ontologies/abc/c2sim_combined.ttl",
    ]
    assert extras["derive_from_ontologies"] == [
        "/var/tkeir/ingest/uploaded_ontologies/abc/c2sim_combined.ttl",
    ]


def test_ontology_upload_decode_rejects_path_strings():
    import base64
    import tempfile
    from pathlib import Path

    from thot.tools.ingest.ontology_upload import (
        decode_ontology_uploads,
        stage_ontology_bytes,
    )

    try:
        decode_ontology_uploads(["/client/path.ttl"])
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "content" in str(exc).lower() or "path" in str(exc).lower()

    payload = base64.b64encode(b"@prefix : <http://ex/> .").decode()
    items = decode_ontology_uploads(
        [{"filename": "mini.ttl", "content_base64": payload}]
    )
    assert items[0][0] == "mini.ttl"
    with tempfile.TemporaryDirectory() as tmp:
        staged = stage_ontology_bytes(Path(tmp), items)
        assert len(staged) == 1
        assert Path(staged[0]).read_bytes().startswith(b"@prefix")


def test_preserve_pipeline_extras_keeps_derive_from_after_convert():
    from thot.tasks.pipeline.PipelineRunner import _preserve_pipeline_extras

    source = {
        "datatype": "txt",
        "data": "x",
        "source": "ingest://a.txt",
        "ontologies": ["datasets/osint/ontologies/c2sim_core.owl"],
        "derive_from_ontologies": ["datasets/osint/ontologies/c2sim_core.owl"],
        "corpus": "osint",
        "metadata": {"topic_id": "t1"},
    }
    converted = {"content": ["hello"], "source_doc_id": "abc"}
    out = _preserve_pipeline_extras(source, converted)
    assert out["ontologies"] == ["datasets/osint/ontologies/c2sim_core.owl"]
    assert out["derive_from_ontologies"] == [
        "datasets/osint/ontologies/c2sim_core.owl"
    ]
    assert out["corpus"] == "osint"
    assert out["metadata"]["topic_id"] == "t1"


def test_ontology_lexicon_phrase_match():
    from thot.tasks.document_ontology.OntologyLexicon import (
        match_ontology_phrases_in_tokens,
        ontology_paths_from_document,
        stamp_document_ontologies,
    )

    spans = match_ontology_phrases_in_tokens(
        [{"text": "Ground"}, {"text": "Unit"}, {"text": "ready"}],
        [("ground", "unit")],
    )
    assert spans == [
        {
            "start": 0,
            "end": 2,
            "label": "concept",
            "text": "Ground Unit",
        }
    ]
    doc = stamp_document_ontologies({}, ["a.ttl", "b.owl"])
    assert ontology_paths_from_document(doc) == ["a.ttl", "b.owl"]


def test_request_ingest_shutdown_is_idempotent(monkeypatch):
    from thot.tools.ingest import shutdown as shutdown_mod

    calls: list[tuple[int, int]] = []

    def fake_kill(pid, sig):
        calls.append((pid, sig))

    monkeypatch.setattr(shutdown_mod, "_shutdown_requested", False)
    monkeypatch.setattr(shutdown_mod, "_shutdown_reason", None)
    monkeypatch.setattr(shutdown_mod.os, "kill", fake_kill)
    shutdown_mod.request_ingest_shutdown("first")
    shutdown_mod.request_ingest_shutdown("second")
    assert len(calls) == 1
    assert shutdown_mod.shutdown_reason() == "first"


def test_ensure_source_doc_id_for_corpus_json():
    from thot.tools.ingest.worker import ensure_source_doc_id

    doc = {"title": "SALUTE", "content": ["body text"]}
    out = ensure_source_doc_id(
        doc, filename="SALUTE_00012.json", content_digest="abc123"
    )
    assert out["source_doc_id"] == "ingest://abc123/SALUTE_00012.json"
    # Idempotent when already set
    out2 = ensure_source_doc_id(
        {"source_doc_id": "keep-me"}, filename="x.json"
    )
    assert out2["source_doc_id"] == "keep-me"


def test_idempotency_key_stable():
    doc_id = "a" * 64
    pipeline_sha = "b" * 64
    embedder_sha = "c" * 64
    assert idempotency_key(
        doc_id, pipeline_sha, embedder_sha
    ) == idempotency_key(
        doc_id,
        pipeline_sha,
        embedder_sha,
    )


def test_embedder_fingerprint():
    digest = embedder_fingerprint(provider="ollama", model="bge-m3")
    assert len(digest) == 64


def test_store_manifest_roundtrip(ingest_root):
    store = IngestStore(ingest_root)
    store.ensure_layout()
    manifest = IngestManifest(
        ingest_id="0" * 26,
        correlation_id="1" * 32,
        doc_id="2" * 64,
        source=SourceInfo(uri="file:///tmp/x.pdf", filename="x.pdf"),
        pipeline_config_sha256="3" * 64,
        embedder=EmbedderInfo(
            model="bge-m3",
            provider="ollama",
            sha256="4" * 64,
        ),
        created_at="2026-01-01T00:00:00.000Z",
    )
    store.write_manifest(manifest)
    loaded = store.read_manifest("2" * 64)
    assert loaded is not None
    assert loaded.ingest_id == manifest.ingest_id


def test_store_analyzed_document_by_source_ref(ingest_root):
    store = IngestStore(ingest_root)
    store.ensure_layout()
    payload = {
        "source_doc_id": "demo/C2-202606-0001",
        "title": "OSINT Report",
        "document_ontology": {"json_ld": '{"@graph":[{"@id":"urn:x"}]}'},
        "core_concepts": [{"concept_id": "DOMAIN:OSINT_SOCMINT"}],
    }
    store.write_analyzed_document(
        "abc123",
        payload,
        source_ref="demo/C2-202606-0001",
    )
    loaded = store.read_analyzed_document("abc123")
    assert loaded is not None
    assert loaded["title"] == "OSINT Report"
    by_ref = store.read_analyzed_document_by_source_ref("demo/C2-202606-0001")
    assert by_ref is not None
    assert by_ref["document_ontology"]["json_ld"]


def test_fetch_local_file(ingest_root):
    sample = ingest_root / "sample.txt"
    sample.write_text("payload", encoding="utf-8")
    content, name, _ctype = asyncio.run(fetch_bytes(f"file://{sample}"))
    assert content == b"payload"
    assert name == "sample.txt"


def test_worker_idempotent_noop(ingest_root, monkeypatch):
    ingest_settings.cache_clear()
    monkeypatch.setenv("INGEST_INDEX_ENABLED", "false")
    store = IngestStore(ingest_root)
    worker = IngestWorker(store)
    content = b"same-bytes"
    doc_id = doc_id_from_content(content)

    def fake_pipeline(_runner, _content, _filename, _cid):
        return {
            "source_doc_id": doc_id,
            "content": ["hi"],
            "golden_chunks": [],
        }

    worker._pipeline_fn = fake_pipeline

    job1 = asyncio.run(
        worker.process_source(
            ingest_id="A" * 26,
            correlation_id="c" * 32,
            source_uri="upload://test/doc.txt",
            content=content,
            filename="doc.txt",
        )
    )
    assert job1.status == IngestJobStatus.SUCCEEDED

    job2 = asyncio.run(
        worker.process_source(
            ingest_id="B" * 26,
            correlation_id="c" * 32,
            source_uri="upload://test/doc.txt",
            content=content,
            filename="doc.txt",
        )
    )
    assert job2.status == IngestJobStatus.NOOP
    assert job2.noop is True


def test_worker_writes_dlq_on_pipeline_failure(ingest_root):
    store = IngestStore(ingest_root)
    worker = IngestWorker(store)

    def boom(_runner, _content, _filename, _cid):
        raise RuntimeError("pipeline failed")

    worker._pipeline_fn = boom
    job = asyncio.run(
        worker.process_source(
            ingest_id="D" * 26,
            correlation_id="e" * 32,
            source_uri="upload://test/doc.txt",
            content=b"fail-me",
            filename="doc.txt",
        )
    )
    assert job.status == IngestJobStatus.FAILED
    assert store.read_dlq("D" * 26) is not None


def test_api_health_and_ingest(ingest_root, monkeypatch):
    ingest_settings.cache_clear()
    from thot.tools.ingest import app as ingest_app

    async def fake_process(*_args, **_kwargs):
        return IngestJob(
            ingest_id="F" * 26,
            correlation_id="g" * 32,
            status=IngestJobStatus.SUCCEEDED,
            created_at="2026-01-01T00:00:00.000Z",
            updated_at="2026-01-01T00:00:00.000Z",
        )

    with (
        patch.object(
            ingest_app.VespaClient,
            "health",
            new=AsyncMock(return_value=True),
        ),
        patch.object(
            ingest_app.VespaClient,
            "aclose",
            new=AsyncMock(),
        ),
        patch.object(
            ingest_app.IngestWorker,
            "process_source",
            new=fake_process,
        ),
    ):
        with TestClient(ingest_app.app) as client:
            health = client.get("/health")
            assert health.status_code == 200
            sample = ingest_root / "doc.txt"
            sample.write_text("hello", encoding="utf-8")
            response = client.post(
                "/ingest/document",
                json={"url": f"file://{sample}"},
            )
            assert response.status_code == 202
            body = response.json()
            assert "ingest_id" in body
            assert "correlation_id" in body
            files = {"file": ("upload.txt", b"multipart", "text/plain")}
            multipart = client.post("/ingest/document", files=files)
            assert multipart.status_code == 202


def test_api_status_not_found(ingest_root):
    ingest_settings.cache_clear()
    from thot.tools.ingest import app as ingest_app

    with (
        patch.object(
            ingest_app.VespaClient,
            "health",
            new=AsyncMock(return_value=True),
        ),
        patch.object(
            ingest_app.VespaClient,
            "aclose",
            new=AsyncMock(),
        ),
    ):
        with TestClient(ingest_app.app) as client:
            response = client.get("/ingest/status/" + ("Z" * 26))
            assert response.status_code == 404


def test_auth_dev_token_required(ingest_root, monkeypatch):
    ingest_settings.cache_clear()
    monkeypatch.setenv("INGEST_AUTH_ENABLED", "true")
    monkeypatch.setenv("INGEST_DEV_TOKEN", "secret-token")
    ingest_settings.cache_clear()
    from thot.tools.ingest import app as ingest_app

    with (
        patch.object(
            ingest_app.VespaClient,
            "health",
            new=AsyncMock(return_value=True),
        ),
        patch.object(
            ingest_app.VespaClient,
            "aclose",
            new=AsyncMock(),
        ),
        patch.object(
            ingest_app.IngestWorker,
            "process_source",
            new=AsyncMock(
                return_value=IngestJob(
                    ingest_id="H" * 26,
                    correlation_id="i" * 32,
                    status=IngestJobStatus.PENDING,
                    created_at="2026-01-01T00:00:00.000Z",
                    updated_at="2026-01-01T00:00:00.000Z",
                )
            ),
        ),
    ):
        with TestClient(ingest_app.app) as client:
            denied = client.post(
                "/ingest/document",
                json={"url": "file:///etc/hosts"},
            )
            assert denied.status_code == 401
            allowed = client.post(
                "/ingest/document",
                json={"url": "file:///etc/hosts"},
                headers={"Authorization": "Bearer secret-token"},
            )
            assert allowed.status_code == 202


def test_pipeline_config_sha256(ingest_root):
    path = ingest_root / "pipeline.yaml"
    path.write_text("tasks: []\n", encoding="utf-8")
    digest = pipeline_config_sha256(path)
    assert len(digest) == 64


def test_auth_jwt_prefers_preferred_username(ingest_root, monkeypatch):
    import base64
    import json

    ingest_settings.cache_clear()
    monkeypatch.setenv("INGEST_AUTH_ENABLED", "true")
    ingest_settings.cache_clear()
    from thot.tools.ingest.auth import verify_ingest_authorization

    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {
                    "scope": "openid intent:ingest",
                    "preferred_username": "demo-user",
                    "email": "demo-user@tkeir",
                    "sub": "uuid-ignore",
                }
            ).encode()
        )
        .decode()
        .rstrip("=")
    )
    token = f"header.{payload}.sig"
    assert verify_ingest_authorization(f"Bearer {token}") == "demo-user"


def test_resolve_allowed_index_target_non_admin_forced_user(
    ingest_root, monkeypatch
):
    import base64
    import json

    from fastapi import HTTPException

    ingest_settings.cache_clear()
    monkeypatch.setenv("INGEST_AUTH_ENABLED", "true")
    ingest_settings.cache_clear()
    from thot.tools.ingest.auth import resolve_allowed_index_target

    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {
                    "scope": "openid intent:ingest",
                    "preferred_username": "analyst",
                    "realm_access": {"roles": ["c2-j2-analyst", "tkeir-user"]},
                }
            ).encode()
        )
        .decode()
        .rstrip("=")
    )
    auth = f"Bearer header.{payload}.sig"
    assert (
        resolve_allowed_index_target(None, authorization=auth, default="user")
        == "user"
    )
    try:
        resolve_allowed_index_target("global", authorization=auth)
        raise AssertionError("expected 403")
    except HTTPException as exc:
        assert exc.status_code == 403


def test_resolve_allowed_index_target_admin_global(ingest_root, monkeypatch):
    import base64
    import json

    ingest_settings.cache_clear()
    monkeypatch.setenv("INGEST_AUTH_ENABLED", "true")
    ingest_settings.cache_clear()
    from thot.tools.ingest.auth import resolve_allowed_index_target

    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {
                    "scope": "openid intent:ingest",
                    "preferred_username": "c2-admin",
                    "realm_access": {"roles": ["c2-admin", "tkeir-admin"]},
                }
            ).encode()
        )
        .decode()
        .rstrip("=")
    )
    auth = f"Bearer header.{payload}.sig"
    assert (
        resolve_allowed_index_target(
            None, authorization=auth, admin_default="global"
        )
        == "global"
    )
    assert resolve_allowed_index_target("both", authorization=auth) == "both"


def test_auth_disabled_uses_dev_user_space(ingest_root, monkeypatch):
    ingest_settings.cache_clear()
    monkeypatch.delenv("VESPA_USER_SPACE", raising=False)
    monkeypatch.setenv("INGEST_AUTH_ENABLED", "false")
    ingest_settings.cache_clear()
    from thot.tools.ingest.auth import verify_ingest_authorization

    assert verify_ingest_authorization(None) == "dev@tkeir"


def test_auth_resource_access_role(ingest_root, monkeypatch):
    import base64
    import json

    ingest_settings.cache_clear()
    monkeypatch.setenv("INGEST_AUTH_ENABLED", "true")
    ingest_settings.cache_clear()
    from thot.tools.ingest.auth import verify_ingest_authorization

    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {
                    "resource_access": {"tkeir-ingest": {"roles": ["ingest"]}},
                    "sub": "svc-1",
                }
            ).encode()
        )
        .decode()
        .rstrip("=")
    )
    token = f"header.{payload}.sig"
    assert verify_ingest_authorization(f"Bearer {token}") == "svc-1"


def test_auth_rejects_missing_scope(ingest_root, monkeypatch):
    import base64
    import json

    ingest_settings.cache_clear()
    monkeypatch.setenv("INGEST_AUTH_ENABLED", "true")
    ingest_settings.cache_clear()
    from fastapi import HTTPException

    from thot.tools.ingest.auth import verify_ingest_authorization

    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"scope": "openid", "sub": "user-1"}).encode()
        )
        .decode()
        .rstrip("=")
    )
    token = f"header.{payload}.sig"
    with pytest.raises(HTTPException) as exc:
        verify_ingest_authorization(f"Bearer {token}")
    assert exc.value.status_code == 403


def test_api_batch_ingest(ingest_root):
    ingest_settings.cache_clear()
    from thot.tools.ingest import app as ingest_app

    async def fake_process(*_args, **_kwargs):
        return IngestJob(
            ingest_id="J" * 26,
            correlation_id="k" * 32,
            status=IngestJobStatus.SUCCEEDED,
            created_at="2026-01-01T00:00:00.000Z",
            updated_at="2026-01-01T00:00:00.000Z",
        )

    sample = ingest_root / "a.txt"
    sample.write_text("a", encoding="utf-8")
    with (
        patch.object(
            ingest_app.VespaClient,
            "health",
            new=AsyncMock(return_value=True),
        ),
        patch.object(
            ingest_app.VespaClient,
            "aclose",
            new=AsyncMock(),
        ),
        patch.object(
            ingest_app.IngestWorker,
            "process_source",
            new=fake_process,
        ),
    ):
        with TestClient(ingest_app.app) as client:
            response = client.post(
                "/ingest/batch",
                json={"items": [{"url": f"file://{sample}"}]},
            )
            assert response.status_code == 202
            body = response.json()
            assert body["batch_id"]
            assert len(body["jobs"]) == 1


def test_api_ready_and_metrics(ingest_root):
    ingest_settings.cache_clear()
    from thot.tools.ingest import app as ingest_app

    with (
        patch.object(
            ingest_app.VespaClient,
            "health",
            new=AsyncMock(return_value=True),
        ),
        patch.object(
            ingest_app.VespaClient,
            "aclose",
            new=AsyncMock(),
        ),
        patch(
            "thot.tools.ingest.app.readiness_report",
            new=AsyncMock(
                return_value={"status": "ready", "checks": {}},
            ),
        ),
    ):
        with TestClient(ingest_app.app) as client:
            ready = client.get("/ready")
            assert ready.status_code == 200
            metrics = client.get("/metrics")
            assert metrics.status_code == 200
            assert b"tkeir" in metrics.content or metrics.content


def test_cli_retry_from_dlq(ingest_root, monkeypatch):
    ingest_settings.cache_clear()
    store = IngestStore(ingest_root)
    store.ensure_layout()
    now = "2026-01-01T00:00:00.000Z"
    job = IngestJob(
        ingest_id="L" * 26,
        correlation_id="m" * 32,
        status=IngestJobStatus.FAILED,
        doc_id="n" * 64,
        created_at=now,
        updated_at=now,
    )
    store.write_job(job)
    manifest = IngestManifest(
        ingest_id="L" * 26,
        correlation_id="m" * 32,
        doc_id="n" * 64,
        source=SourceInfo(uri="upload://x", filename="doc.txt"),
        pipeline_config_sha256="o" * 64,
        embedder=EmbedderInfo(
            model="bge-m3",
            provider="ollama",
            sha256="p" * 64,
        ),
        created_at=now,
    )
    store.stage_bytes("n" * 64, b"bytes", filename="doc.txt")
    store.write_dlq("L" * 26, job=job, manifest=manifest, reason="fail")

    from thot.tools.ingest import cli as ingest_cli

    async def fake_retry(_self, ingest_id: str):
        assert ingest_id == "L" * 26
        return IngestJob(
            ingest_id="R" * 26,
            correlation_id="m" * 32,
            status=IngestJobStatus.SUCCEEDED,
            created_at=now,
            updated_at=now,
        )

    with patch.object(
        ingest_cli.IngestWorker, "retry_from_dlq", new=fake_retry
    ):
        with pytest.raises(SystemExit) as exc:
            ingest_cli.main(["retry", "--from-dlq", "--ingest-id", "L" * 26])
        assert exc.value.code == 0


def test_worker_retry_from_dlq(ingest_root):
    store = IngestStore(ingest_root)
    worker = IngestWorker(store)
    content = b"retry-bytes"
    doc_id = doc_id_from_content(content)
    now = "2026-01-01T00:00:00.000Z"
    failed_job = IngestJob(
        ingest_id="M" * 26,
        correlation_id="q" * 32,
        status=IngestJobStatus.FAILED,
        doc_id=doc_id,
        created_at=now,
        updated_at=now,
        error="simulated",
    )
    store.write_job(failed_job)
    manifest = IngestManifest(
        ingest_id="M" * 26,
        correlation_id="q" * 32,
        doc_id=doc_id,
        source=SourceInfo(uri="upload://test/doc.txt", filename="doc.txt"),
        pipeline_config_sha256="o" * 64,
        embedder=EmbedderInfo(
            model="bge-m3",
            provider="ollama",
            sha256="p" * 64,
        ),
        created_at=now,
    )
    store.stage_bytes(doc_id, content, filename="doc.txt")
    store.write_manifest(manifest)
    store.write_dlq(
        "M" * 26, job=failed_job, manifest=manifest, reason="simulated"
    )

    def fake_pipeline(_runner, _content, _filename, _cid):
        return {
            "source_doc_id": doc_id,
            "content": ["hi"],
            "golden_chunks": [],
        }

    worker._pipeline_fn = fake_pipeline
    retried = asyncio.run(worker.retry_from_dlq("M" * 26))
    assert retried.status in {
        IngestJobStatus.SUCCEEDED,
        IngestJobStatus.NOOP,
    }


def test_intent_for_path_ingest():
    from thot.action.middleware import intent_for_path

    assert intent_for_path("/ingest/document") == "ingest"
    assert intent_for_path("/ingest/batch") == "ingest"


def test_fetch_http_url():
    from unittest.mock import MagicMock

    response = MagicMock()
    response.content = b"remote"
    response.headers = {"content-type": "text/plain"}
    response.raise_for_status = MagicMock()
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.aclose = AsyncMock()
    content, name, ctype = asyncio.run(
        fetch_bytes("https://example.com/doc.pdf", client=client)
    )
    assert content == b"remote"
    assert name == "doc.pdf"
    assert ctype == "text/plain"


def test_worker_fetch_failure(ingest_root):
    store = IngestStore(ingest_root)
    worker = IngestWorker(store)
    job = asyncio.run(
        worker.process_source(
            ingest_id="S" * 26,
            correlation_id="t" * 32,
            source_uri="https://missing.example/nope",
            content=None,
            filename="doc.txt",
        )
    )
    assert job.status == IngestJobStatus.FAILED
    assert store.read_dlq("S" * 26) is not None


def test_api_ingest_status_ok(ingest_root):
    ingest_settings.cache_clear()
    from thot.tools.ingest import app as ingest_app

    now = "2026-01-01T00:00:00.000Z"
    job = IngestJob(
        ingest_id="U" * 26,
        correlation_id="v" * 32,
        status=IngestJobStatus.SUCCEEDED,
        doc_id="w" * 64,
        created_at=now,
        updated_at=now,
    )
    store = IngestStore(ingest_root)
    store.ensure_layout()
    store.write_job(job)

    with (
        patch.object(
            ingest_app.VespaClient,
            "health",
            new=AsyncMock(return_value=True),
        ),
        patch.object(
            ingest_app.VespaClient,
            "aclose",
            new=AsyncMock(),
        ),
    ):
        with TestClient(ingest_app.app) as client:
            response = client.get(f"/ingest/status/{'U' * 26}")
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "succeeded"
            # Progress polling must stay light — no manifest unless requested.
            assert payload.get("manifest") is None

            with_manifest = client.get(
                f"/ingest/status/{'U' * 26}?include_manifest=true"
            )
            assert with_manifest.status_code == 200
            assert with_manifest.json()["status"] == "succeeded"


def test_app_main_dispatches_retry(monkeypatch):
    import sys

    from thot.tools.ingest import app as ingest_app

    called = {"cli": False}

    def fake_cli_main(args=None):
        called["cli"] = True

    monkeypatch.setattr("thot.tools.ingest.cli.main", fake_cli_main)
    monkeypatch.setattr(
        sys,
        "argv",
        ["tkeir-ingest", "retry", "--from-dlq", "--ingest-id", "x"],
    )
    ingest_app.main()
    assert called["cli"] is True


def test_cli_retry_missing_dlq(ingest_root, monkeypatch, capsys):
    ingest_settings.cache_clear()
    from thot.tools.ingest import cli as ingest_cli

    with pytest.raises(SystemExit) as exc:
        ingest_cli.main(["retry", "--from-dlq", "--ingest-id", "Z" * 26])
    assert exc.value.code == 1


def test_auth_invalid_jwt(ingest_root, monkeypatch):
    ingest_settings.cache_clear()
    monkeypatch.setenv("INGEST_AUTH_ENABLED", "true")
    ingest_settings.cache_clear()
    from fastapi import HTTPException

    from thot.tools.ingest.auth import verify_ingest_authorization

    with pytest.raises(HTTPException) as exc:
        verify_ingest_authorization("Bearer not-a-jwt")
    assert exc.value.status_code == 401


def test_api_ready_not_ready(ingest_root):
    ingest_settings.cache_clear()
    from thot.tools.ingest import app as ingest_app

    with (
        patch.object(
            ingest_app.VespaClient,
            "health",
            new=AsyncMock(return_value=True),
        ),
        patch.object(
            ingest_app.VespaClient,
            "aclose",
            new=AsyncMock(),
        ),
        patch(
            "thot.tools.ingest.app.readiness_report",
            new=AsyncMock(return_value={"status": "not_ready", "checks": {}}),
        ),
    ):
        with TestClient(ingest_app.app) as client:
            response = client.get("/ready")
            assert response.status_code == 503


def test_fetch_unsupported_scheme():
    from thot.tools.ingest.fetch import FetchError

    with pytest.raises(FetchError):
        asyncio.run(fetch_bytes("ftp://example.com/x"))


def test_fetch_file_missing():
    from thot.tools.ingest.fetch import FetchError

    with pytest.raises(FetchError):
        asyncio.run(fetch_bytes("file:///no/such/file.bin"))


def test_api_health_vespa_down(ingest_root):
    ingest_settings.cache_clear()
    from thot.tools.ingest import app as ingest_app

    with (
        patch.object(
            ingest_app.VespaClient,
            "health",
            new=AsyncMock(return_value=False),
        ),
        patch.object(
            ingest_app.VespaClient,
            "aclose",
            new=AsyncMock(),
        ),
        patch(
            "thot.tools.ingest.app.readiness_report",
            new=AsyncMock(
                return_value={"status": "not_ready", "vespa": False}
            ),
        ),
    ):
        with TestClient(ingest_app.app) as client:
            # Liveness stays up even if Vespa is down; readiness fails.
            assert client.get("/health").status_code == 200
            assert client.get("/ready").status_code == 503


def test_auth_missing_bearer(ingest_root, monkeypatch):
    ingest_settings.cache_clear()
    monkeypatch.setenv("INGEST_AUTH_ENABLED", "true")
    ingest_settings.cache_clear()
    from fastapi import HTTPException

    from thot.tools.ingest.auth import verify_ingest_authorization

    with pytest.raises(HTTPException) as exc:
        verify_ingest_authorization(None)
    assert exc.value.status_code == 401
