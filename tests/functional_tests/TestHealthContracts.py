"""Cross-service health / readiness contracts (offline TestClient)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


def test_ingest_health_ready_metrics(ingest_harness):
    client, _root = ingest_harness
    assert client.get("/health").status_code == 200
    ready = client.get("/ready")
    assert ready.status_code in {200, 503}
    metrics = client.get("/metrics")
    assert metrics.status_code == 200


def test_okf_health_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("OKF_ROOT", str(tmp_path / "okf"))
    monkeypatch.setenv("GOVERNOR_MODE", "off")
    from thot.okf import server as okf_server

    with TestClient(okf_server.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        ready = client.get("/ready")
        assert ready.status_code in {200, 503}
        bundles = client.get("/okf/bundles")
        assert bundles.status_code == 200
        missing = client.get("/okf/bundles/no-such-bundle")
        assert missing.status_code == 404


def test_rag_request_models_reject_empty_query():
    """Pydantic contract shared by /search and /rag/query (no lifespan)."""
    import pytest
    from pydantic import ValidationError

    from thot.tools.search.app import QueryRequest, SearchRequest

    with pytest.raises(ValidationError):
        SearchRequest(query="")
    with pytest.raises(ValidationError):
        QueryRequest(query="")
    ok = SearchRequest(query="smoke", hits=1, language="en")
    assert ok.hits == 1


def test_rag_health_with_mocked_lifespan(monkeypatch):
    """Spin RAG app with mocked Vespa/LLM — assert health + validation only."""
    monkeypatch.setenv("GOVERNOR_MODE", "off")

    from thot.tools.search import app as rag_app

    llm = MagicMock()
    llm.verify_provider = AsyncMock()
    llm.aclose = AsyncMock()
    vespa = MagicMock()
    vespa.health = AsyncMock(return_value=True)
    vespa.aclose = AsyncMock()

    with (
        patch.object(rag_app, "UnifiedLLMWrapper", return_value=llm),
        patch.object(rag_app, "VespaClient", return_value=vespa),
        patch.object(rag_app, "_load_pipeline_runners", return_value={}),
    ):
        with TestClient(rag_app.app) as client:
            health = client.get("/health")
            assert health.status_code == 200
            empty = client.post("/search", json={"query": ""})
            assert empty.status_code == 422
            missing = client.post("/search", json={})
            assert missing.status_code == 422
            rag_empty = client.post("/rag/query", json={"query": ""})
            assert rag_empty.status_code == 422
