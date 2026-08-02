"""Session fixtures for live RAG / ingest integration tests.

Skips the whole suite when the RAG service is unreachable so ``make ci`` can
still pass without a running Compose stack.
"""

from __future__ import annotations

import os

import pytest
import requests

RAG_URL = os.environ.get("RAG_URL", "http://localhost:8090").rstrip("/")
INGEST_URL = os.environ.get(
    "INGEST_URL", os.environ.get("INGEST_URL_TEST", f"{RAG_URL}/ingest")
).rstrip("/")


def _service_reachable(url: str, timeout: float = 2.0) -> bool:
    try:
        response = requests.get(f"{url}/health", timeout=timeout)
        return response.status_code < 500
    except requests.RequestException:
        return False


@pytest.fixture(scope="session", autouse=True)
def _skip_when_rag_down() -> None:
    """Skip the entire integration session when RAG is not reachable."""
    if not _service_reachable(RAG_URL):
        pytest.skip(
            f"RAG service unreachable at {RAG_URL}/health — "
            "start with `make compose-up` or `make rag`",
        )


@pytest.fixture(scope="session")
def rag_url() -> str:
    """Base URL for the RAG API (session-scoped)."""
    return RAG_URL


@pytest.fixture(scope="session")
def ingest_url() -> str:
    """Ingest API base URL (defaults to ``RAG_URL/ingest`` or ``INGEST_URL``)."""
    return INGEST_URL


@pytest.fixture(scope="session")
def http_session() -> requests.Session:
    """Shared requests session for integration tests."""
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    return session
