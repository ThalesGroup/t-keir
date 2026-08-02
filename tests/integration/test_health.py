"""Live stack smoke checks for RAG (+ optional ingest) health endpoints."""

from __future__ import annotations

import requests


def test_rag_health(rag_url: str, http_session: requests.Session) -> None:
    response = http_session.get(f"{rag_url}/health", timeout=5)
    assert response.status_code == 200


def test_rag_ready_or_health(
    rag_url: str, http_session: requests.Session
) -> None:
    ready = http_session.get(f"{rag_url}/ready", timeout=5)
    if ready.status_code == 404:
        health = http_session.get(f"{rag_url}/health", timeout=5)
        assert health.status_code == 200
        return
    assert ready.status_code in {200, 503}


def test_ingest_health_best_effort(
    ingest_url: str, http_session: requests.Session
) -> None:
    """Ingest may share the RAG host or run on :8091 — soft check."""
    try:
        response = http_session.get(f"{ingest_url}/health", timeout=2)
    except requests.RequestException:
        return
    assert response.status_code < 500
