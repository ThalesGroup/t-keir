"""Title: MCP tool handlers — tenant-scoped wrappers over Vespa / ontology utils.

``user_space`` is always injected by authz; client arguments never set it.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from thot.core.ThotMetrics import ThotMetrics
from thot.mcp.authz import McpPrincipal, strip_tenant_overrides
from thot.tools.search.vespa_client import (
    VespaClient,
    document_vespa_id,
    normalize_user_space,
)

LOGGER = logging.getLogger(__name__)

_METRICS_READY = False


def _ensure_metrics() -> None:
    global _METRICS_READY
    if _METRICS_READY:
        return
    ThotMetrics.create_counter(
        short_name="mcp_tool_calls",
        function_name="mcp_tool_calls_total",
        counter_description="MCP tool invocations",
    )
    _METRICS_READY = True


class McpBackend(Protocol):
    """Injectable search/document backend for handlers and tests."""

    async def hybrid_search(
        self,
        query: str,
        *,
        hits: int,
        user_space: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Run hybrid search in ``user_space``."""

    async def rag_query(
        self,
        query: str,
        *,
        hits: int,
        user_space: str,
        language: str | None = None,
        generate: bool = True,
    ) -> dict[str, Any]:
        """Run RAG (or retrieval-only) in ``user_space``."""

    async def get_document(
        self,
        *,
        user_space: str,
        source_doc_id: str | None = None,
        doc_ref: str | None = None,
    ) -> dict[str, Any]:
        """Fetch one parent document; must enforce ``user_space``."""

    async def ontology_from_query(
        self,
        query: str,
        *,
        hits: int,
        user_space: str,
        max_triples: int = 40,
    ) -> dict[str, Any]:
        """Build ontology summary from docs in ``user_space``."""


class VespaMcpBackend:
    """Default backend using :class:`VespaClient` (+ optional RAG HTTP)."""

    def __init__(self, vespa: VespaClient | None = None) -> None:
        self._vespa = vespa or VespaClient()

    async def hybrid_search(
        self,
        query: str,
        *,
        hits: int,
        user_space: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        space = normalize_user_space(user_space)
        # Zero vectors → BM25-heavy path still applies streaming.groupname.
        dim = int(self._vespa.config.embedding_dim or 384)
        zeros = [0.0] * dim
        response = await self._vespa.hybrid_search(
            query,
            zeros,
            zeros,
            hits=hits,
            user_space=space,
        )
        children = (
            ((response.get("root") or {}).get("children"))
            if isinstance(response, dict)
            else None
        ) or []
        chunks: list[dict[str, Any]] = []
        for child in children:
            fields = (child or {}).get("fields") or {}
            chunk_space = str(fields.get("user_space") or space)
            if normalize_user_space(chunk_space) != space:
                continue
            chunks.append(
                {
                    "chunk_id": fields.get("chunk_id"),
                    "parent_doc_id": (
                        fields.get("parent_doc_id")
                        or fields.get("source_doc_id")
                    ),
                    "text_raw": fields.get("text_raw") or fields.get("text"),
                    "score": (child or {}).get("relevance"),
                    "user_space": space,
                }
            )
        return {
            "query": query,
            "user_space": space,
            "language": language,
            "chunks": chunks,
            "vespa_hits": len(children),
        }

    async def rag_query(
        self,
        query: str,
        *,
        hits: int,
        user_space: str,
        language: str | None = None,
        generate: bool = True,
    ) -> dict[str, Any]:
        import os

        import httpx

        space = normalize_user_space(user_space)
        rag_url = (
            os.getenv("MCP_RAG_URL") or os.getenv("RAG_URL") or ""
        ).rstrip("/")
        if rag_url and generate:
            headers: dict[str, str] = {}
            # Prefer propagating the caller's JWT when present via env bridge —
            # handlers pass authorization through principal when calling HTTP.
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{rag_url}/rag/query",
                    json={
                        "query": query,
                        "hits": hits,
                        "language": language,
                    },
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
            payload["user_space"] = space
            return payload

        retrieved = await self.hybrid_search(
            query, hits=hits, user_space=space, language=language
        )
        return {
            "query": query,
            "user_space": space,
            "answer": None,
            "report_markdown": None,
            "generate": False,
            "chunks": retrieved.get("chunks") or [],
            "note": "retrieval-only (set MCP_RAG_URL for full RAG generation)",
        }

    async def get_document(
        self,
        *,
        user_space: str,
        source_doc_id: str | None = None,
        doc_ref: str | None = None,
    ) -> dict[str, Any]:
        space = normalize_user_space(user_space)
        if not source_doc_id and not doc_ref:
            raise ValueError("source_doc_id or doc_ref is required")
        ref = doc_ref or document_vespa_id(
            str(source_doc_id), user_space=space
        )
        # Reject cross-tenant Vespa ids (``g=<group>`` or ``/group/<g>/``).
        if ":g=" in ref:
            after = ref.split(":g=", 1)[1]
            group = after.split(":", 1)[0]
            if group and normalize_user_space(group) != space:
                raise PermissionError(
                    f"document_get denied: doc group {group!r} "
                    f"!= caller user_space {space!r}"
                )
        if "/group/" in ref:
            marker = "/group/"
            idx = ref.find(marker)
            rest = ref[idx + len(marker) :]
            group = rest.split("/", 1)[0]
            if normalize_user_space(group) != space:
                raise PermissionError(
                    f"document_get denied: doc group {group!r} "
                    f"!= caller user_space {space!r}"
                )
        fields = await self._vespa.get_document_by_ref(ref)
        field_space = fields.get("user_space")
        if (
            field_space is not None
            and normalize_user_space(str(field_space)) != space
        ):
            raise PermissionError(
                f"document_get denied: document user_space "
                f"{field_space!r} != caller {space!r}"
            )
        return {
            "user_space": space,
            "doc_ref": ref,
            "source_doc_id": fields.get("source_doc_id") or source_doc_id,
            "fields": {
                k: v
                for k, v in fields.items()
                if k
                not in {
                    # keep payload bounded for MCP
                }
            },
        }

    async def ontology_from_query(
        self,
        query: str,
        *,
        hits: int,
        user_space: str,
        max_triples: int = 40,
    ) -> dict[str, Any]:
        from thot.tools.search.ontology_utils import (
            merge_rdf_graphs,
            summarize_graph_for_prompt,
        )

        space = normalize_user_space(user_space)
        retrieved = await self.hybrid_search(
            query, hits=hits, user_space=space
        )
        turtles: list[str] = []
        parent_ids: list[str] = []
        for chunk in retrieved.get("chunks") or []:
            parent = chunk.get("parent_doc_id")
            if not parent or parent in parent_ids:
                continue
            parent_ids.append(str(parent))
            try:
                doc = await self.get_document(
                    user_space=space, source_doc_id=str(parent)
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("ontology skip parent %s: %s", parent, exc)
                continue
            fields = doc.get("fields") or {}
            rdf = (
                fields.get("json_ld")
                or fields.get("rdf_graph_serialized")
                or fields.get("ontology_turtle")
                or fields.get("ontology")
            )
            if isinstance(rdf, str) and rdf.strip():
                turtles.append(rdf)

        if not turtles:
            return {
                "user_space": space,
                "query": query,
                "summary": "",
                "document_ids": parent_ids,
                "triple_count": 0,
            }
        graph = merge_rdf_graphs(turtles)
        summary = summarize_graph_for_prompt(
            graph, query, max_triples=max_triples
        )
        return {
            "user_space": space,
            "query": query,
            "summary": summary,
            "document_ids": parent_ids,
            "triple_count": len(graph),
        }


class McpHandlers:
    """Dispatch MCP tools with forced ``user_space`` and metrics."""

    def __init__(self, backend: McpBackend | None = None) -> None:
        self.backend: McpBackend = backend or VespaMcpBackend()

    async def invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        principal: McpPrincipal,
    ) -> dict[str, Any]:
        """Run ``tool_name`` for ``principal.user_space``.

        Example:
            >>> import asyncio
            >>> from thot.mcp.authz import McpPrincipal
            >>> from thot.mcp.handlers import McpHandlers

            >>> class _Stub:
            ...     async def hybrid_search(self, query, **kw):
            ...         return {"query": query, "user_space": kw["user_space"], "chunks": []}
            ...     async def rag_query(self, query, **kw):
            ...         return await self.hybrid_search(query, **kw)
            ...     async def get_document(self, **kw):
            ...         return {"user_space": kw["user_space"], "fields": {}}
            ...     async def ontology_from_query(self, query, **kw):
            ...         return {"user_space": kw["user_space"], "summary": ""}
            >>> h = McpHandlers(backend=_Stub())
            >>> out = asyncio.run(h.invoke(
            ...     "search",
            ...     {"query": "hello", "user_space": "attacker"},
            ...     McpPrincipal(user_space="alice"),
            ... ))
            >>> out["user_space"]
            'alice'
        """
        _ensure_metrics()
        ThotMetrics.increment_counter(
            short_name="mcp_tool_calls",
            method="MCP",
            path=f"/mcp/tools/{tool_name}",
            status=200,
        )
        args = strip_tenant_overrides(dict(arguments or {}))
        space = principal.user_space

        if tool_name == "search":
            return await self.backend.hybrid_search(
                str(args.get("query") or ""),
                hits=int(args.get("hits") or 10),
                user_space=space,
                language=args.get("language"),
            )
        if tool_name == "rag_query":
            return await self.backend.rag_query(
                str(args.get("query") or ""),
                hits=int(args.get("hits") or 8),
                user_space=space,
                language=args.get("language"),
                generate=bool(args.get("generate", True)),
            )
        if tool_name == "ontology_query":
            return await self.backend.ontology_from_query(
                str(args.get("query") or ""),
                hits=int(args.get("hits") or 5),
                user_space=space,
                max_triples=int(args.get("max_triples") or 40),
            )
        if tool_name == "document_get":
            return await self.backend.get_document(
                user_space=space,
                source_doc_id=args.get("source_doc_id"),
                doc_ref=args.get("doc_ref"),
            )
        raise KeyError(f"unknown tool handler: {tool_name}")
