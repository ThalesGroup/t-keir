"""Multi-tenancy tests: MCP handlers never honour foreign user_space."""

from __future__ import annotations

import asyncio

import pytest

from thot.action.sink import InMemoryActionSink
from thot.mcp.authz import McpPrincipal
from thot.mcp.handlers import McpHandlers
from thot.mcp.server import McpRuntime
from thot.tools.search.vespa_client import document_vespa_id


class RecordingBackend:
    """Backend that records the user_space passed into every call."""

    def __init__(self) -> None:
        self.spaces: list[str] = []

    async def hybrid_search(self, query, *, hits, user_space, language=None):
        self.spaces.append(user_space)
        return {
            "query": query,
            "user_space": user_space,
            "chunks": [
                {
                    "chunk_id": "c1",
                    "parent_doc_id": "doc-a",
                    "text_raw": "hello",
                    "user_space": user_space,
                }
            ],
        }

    async def rag_query(self, query, **kwargs):
        return await self.hybrid_search(
            query,
            hits=kwargs.get("hits", 8),
            user_space=kwargs["user_space"],
            language=kwargs.get("language"),
        )

    async def get_document(
        self, *, user_space, source_doc_id=None, doc_ref=None
    ):
        self.spaces.append(user_space)
        if doc_ref and ":g=" in doc_ref:
            group = doc_ref.split(":g=", 1)[1].split(":", 1)[0]
            from thot.tools.search.vespa_client import normalize_user_space

            if normalize_user_space(group) != normalize_user_space(user_space):
                raise PermissionError("cross-tenant doc_ref")
        return {
            "user_space": user_space,
            "source_doc_id": source_doc_id,
            "doc_ref": doc_ref,
            "fields": {"user_space": user_space, "title": "t"},
        }

    async def ontology_from_query(self, query, **kwargs):
        self.spaces.append(kwargs["user_space"])
        return {
            "user_space": kwargs["user_space"],
            "query": query,
            "summary": "",
            "document_ids": [],
            "triple_count": 0,
        }


def test_handler_ignores_client_user_space_override():
    backend = RecordingBackend()
    handlers = McpHandlers(backend=backend)
    principal = McpPrincipal(user_space="alice")
    out = asyncio.run(
        handlers.invoke(
            "search",
            {"query": "q", "user_space": "bob", "group": "bob"},
            principal,
        )
    )
    assert out["user_space"] == "alice"
    assert backend.spaces == ["alice"]


def test_document_get_rejects_foreign_group_in_doc_ref():
    """VespaMcpBackend rejects cross-tenant doc_ref before fetch."""
    from thot.mcp.handlers import VespaMcpBackend

    class _BoomVespa:
        async def get_document_by_ref(self, doc_ref):
            raise AssertionError("must not fetch foreign docs")

    backend = VespaMcpBackend(vespa=_BoomVespa())
    foreign = document_vespa_id("file://secret.pdf", user_space="bob")
    with pytest.raises(PermissionError, match="denied"):
        asyncio.run(backend.get_document(user_space="alice", doc_ref=foreign))


def test_runtime_emits_action_record_with_user_space(monkeypatch):
    sink = InMemoryActionSink()
    monkeypatch.setattr("thot.mcp.server.default_action_sink", lambda: sink)
    runtime = McpRuntime()
    runtime.handlers = McpHandlers(backend=RecordingBackend())
    out = asyncio.run(runtime.call_tool("search", {"query": "hello"}))
    assert out["user_space"] == "dev@tkeir"
    records = list(sink._records)
    assert records
    last = records[-1]
    assert last.ext.get("mcp_tool") == "search"
    assert last.ext.get("user_space") == "dev@tkeir"
    assert last.ext.get("action_kind") == "tool.invoke"
    assert last.intent.declared == "search"


def test_search_never_uses_other_tenant_backend_space():
    backend = RecordingBackend()
    handlers = McpHandlers(backend=backend)
    asyncio.run(
        handlers.invoke(
            "rag_query",
            {"query": "x", "user_space": "attacker@evil"},
            McpPrincipal(user_space="carol"),
        )
    )
    assert backend.spaces == ["carol"]
