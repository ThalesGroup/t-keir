"""Shared fixtures for offline functional HTTP contract tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def ingest_harness(monkeypatch):
    """Isolated ingest API with Vespa/worker mocked and auth disabled."""
    from thot.governor.config import governor_settings
    from thot.tools.ingest.config import ingest_settings

    ingest_settings.cache_clear()
    governor_settings.cache_clear()
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        monkeypatch.setenv("INGEST_ROOT", str(root))
        monkeypatch.setenv("TKEIR_WORKSPACE", str(root / "workspace"))
        monkeypatch.setenv("GOVERNOR_MODE", "off")
        monkeypatch.setenv("GOVERNOR_STATE_ROOT", str(root / "governor"))
        monkeypatch.setenv("INGEST_AUTH_ENABLED", "false")
        monkeypatch.setenv("INGEST_INDEX_ENABLED", "false")
        ingest_settings.cache_clear()
        governor_settings.cache_clear()

        from thot.tools.ingest import app as ingest_app
        from thot.tools.ingest.models import IngestJob, IngestJobStatus

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
                yield client, root

        ingest_settings.cache_clear()
        governor_settings.cache_clear()


@pytest.fixture
def agent_client(monkeypatch, tmp_path):
    """Agent API TestClient with LLM construction mocked."""
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path / "agent"))
    monkeypatch.setenv("GOVERNOR_STATE_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SPIFFE_MODE", "dev")
    monkeypatch.setenv("SPIFFE_ENFORCE", "false")

    from thot.tools.agent import app as agent_app

    llm = MagicMock()
    llm.verify_provider = AsyncMock()
    llm.aclose = AsyncMock()
    with patch.object(agent_app, "UnifiedLLMWrapper", return_value=llm):
        with TestClient(agent_app.app) as client:
            yield client


@pytest.fixture
def governor_client(monkeypatch, tmp_path):
    """Governor API TestClient with auth disabled."""
    from thot.governor.config import governor_settings

    governor_settings.cache_clear()
    monkeypatch.setenv("GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("GOVERNOR_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("GOVERNOR_FLAGS_PATH", str(tmp_path / "flags.json"))
    monkeypatch.setenv("GOVERNOR_BUDGET_DB", str(tmp_path / "budgets.db"))
    monkeypatch.setenv(
        "GOVERNOR_APPROVALS_PATH", str(tmp_path / "approvals.json")
    )
    monkeypatch.setenv("GOVERNOR_AUTH_ENABLED", "false")
    governor_settings.cache_clear()

    from thot.governor import app as governor_app

    with TestClient(governor_app.app) as client:
        yield client
    governor_settings.cache_clear()
