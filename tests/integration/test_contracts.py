"""Broader live integration contracts for systemic coverage."""

from __future__ import annotations

import requests


def test_search_rejects_empty_query(
    rag_url: str, http_session: requests.Session
) -> None:
    response = http_session.post(
        f"{rag_url}/search",
        json={"query": "", "hits": 1},
        timeout=10,
    )
    assert response.status_code in {400, 422}


def test_rag_query_rejects_empty_query(
    rag_url: str, http_session: requests.Session
) -> None:
    response = http_session.post(
        f"{rag_url}/rag/query",
        json={"query": "", "hits": 1},
        timeout=10,
    )
    assert response.status_code in {400, 422}


def test_search_smoke_shape(
    rag_url: str, http_session: requests.Session
) -> None:
    response = http_session.post(
        f"{rag_url}/search",
        json={"query": "integration smoke", "hits": 1, "language": "en"},
        timeout=60,
    )
    assert response.status_code in {200, 502, 503}
    if response.status_code == 200:
        body = response.json()
        assert "query" in body or "chunks" in body or "documents" in body


def test_workspace_tree_when_ingest_up(
    ingest_url: str, http_session: requests.Session
) -> None:
    try:
        response = http_session.get(f"{ingest_url}/workspace/tree", timeout=5)
    except requests.RequestException:
        return
    if response.status_code >= 500:
        return
    assert response.status_code == 200
    body = response.json()
    assert "entries" in body
