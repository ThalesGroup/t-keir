"""Title: MCP tool handlers — tenant-scoped wrappers over Vespa / ontology utils.

``user_space`` is always injected by authz; client arguments never set it.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, cast

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
    """Register MCP tool-call Prometheus counters once per process.

    Example:
        >>> from thot.mcp.handlers import _ensure_metrics
        >>> _ensure_metrics()
    """
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
        search_mode: str | None = None,
    ) -> dict[str, Any]:
        """Run hybrid search in ``user_space`` (optional dual-hybrid mode).

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import McpBackend
            >>> inspect.iscoroutinefunction(McpBackend.hybrid_search)
            True
        """

    async def rag_query(
        self,
        query: str,
        *,
        hits: int,
        user_space: str,
        language: str | None = None,
        generate: bool = True,
        search_mode: str | None = None,
        use_wiki: bool = False,
        wiki_extract: str | None = None,
        wiki_bundle_id: str | None = None,
        agent_id: str | None = None,
        answer_template: str | None = None,
        stop_at_wiki_extract: bool = False,
    ) -> dict[str, Any]:
        """Run RAG (or retrieval-only) in ``user_space``.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import McpBackend
            >>> inspect.iscoroutinefunction(McpBackend.rag_query)
            True
        """

    async def get_document(
        self,
        *,
        user_space: str,
        source_doc_id: str | None = None,
        doc_ref: str | None = None,
    ) -> dict[str, Any]:
        """Fetch one parent document; must enforce ``user_space``.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import McpBackend
            >>> inspect.iscoroutinefunction(McpBackend.get_document)
            True
        """

    async def ontology_from_query(
        self,
        query: str,
        *,
        hits: int,
        user_space: str,
        max_triples: int = 40,
    ) -> dict[str, Any]:
        """Build ontology summary from docs in ``user_space``.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import McpBackend
            >>> inspect.iscoroutinefunction(McpBackend.ontology_from_query)
            True
        """

    async def okf_bundle_list(self, *, user_space: str) -> dict[str, Any]:
        """List OKF bundles for ``user_space``.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import McpBackend
            >>> inspect.iscoroutinefunction(McpBackend.okf_bundle_list)
            True
        """

    async def okf_bundle_get(
        self,
        *,
        user_space: str,
        bundle_id: str,
        concept_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch OKF index / concept markdown for ``user_space``.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import McpBackend
            >>> inspect.iscoroutinefunction(McpBackend.okf_bundle_get)
            True
        """

    async def workspace_wiki_list(
        self, *, user_space: str, path: str = "wiki"
    ) -> dict[str, Any]:
        """List personal-space wiki files.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import McpBackend
            >>> inspect.iscoroutinefunction(McpBackend.workspace_wiki_list)
            True
        """

    async def workspace_wiki_get(
        self, *, user_space: str, path: str
    ) -> dict[str, Any]:
        """Read one personal-space wiki markdown file.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import McpBackend
            >>> inspect.iscoroutinefunction(McpBackend.workspace_wiki_get)
            True
        """

    async def okf_wiki_put(
        self, *, user_space: str, bundle_id: str, markdown: str
    ) -> dict[str, Any]:
        """Write LLMWiki markdown into an OKF bundle.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import McpBackend
            >>> inspect.iscoroutinefunction(McpBackend.okf_wiki_put)
            True
        """


class VespaMcpBackend:
    """Default backend using :class:`VespaClient` (+ optional RAG HTTP)."""

    def __init__(self, vespa: VespaClient | None = None) -> None:
        """Create a backend backed by Vespa (or an injected client).

        Example:
            >>> from thot.mcp.handlers import VespaMcpBackend
            >>> isinstance(VespaMcpBackend(), VespaMcpBackend)
            True
        """
        self._vespa = vespa or VespaClient()

    async def hybrid_search(
        self,
        query: str,
        *,
        hits: int,
        user_space: str,
        language: str | None = None,
        search_mode: str | None = None,
    ) -> dict[str, Any]:
        """Run hybrid search against Vespa for one tenant.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import VespaMcpBackend
            >>> inspect.iscoroutinefunction(VespaMcpBackend.hybrid_search)
            True
        """
        space = normalize_user_space(user_space)
        mode = (search_mode or "").strip().lower() or None
        if mode in {"both", "global", "auto"}:
            try:
                from thot.tools.search.passage_retrieval import (
                    PassageRetrievalPipeline,
                    SearchMode,
                )
                from thot.tools.search.rag_config import load_rag_config

                dual_cfg = load_rag_config().dual_hybrid
                if dual_cfg.enabled:
                    pipeline = PassageRetrievalPipeline(dual_cfg, self._vespa)
                    pipeline_mode = cast(
                        SearchMode,
                        "both" if mode == "auto" else mode,
                    )
                    result = await pipeline.search(
                        query,
                        user_space=space,
                        language=language or "en",
                        mode=pipeline_mode,
                        top_k=hits,
                    )
                    dual_chunks = [
                        {
                            "chunk_id": hit.passage_id,
                            "parent_doc_id": hit.source_ref,
                            "text_raw": hit.chunk_text,
                            "score": hit.score,
                            "user_space": space,
                            "schema": hit.schema,
                        }
                        for hit in result.hits[:hits]
                    ]
                    return {
                        "query": query,
                        "user_space": space,
                        "language": language,
                        "search_mode": result.mode,
                        "chunks": dual_chunks,
                        "vespa_hits": len(dual_chunks),
                    }
            except Exception:  # noqa: BLE001
                LOGGER.exception(
                    "dual-hybrid search failed; falling back to user schema"
                )

        # User-schema BM25/ANN path (or fallback).
        dim = int(self._vespa.config.embedding_dim or 384)
        zeros = [0.0] * dim
        response = await self._vespa.hybrid_search(
            query,
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
            "search_mode": mode or "user",
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
        search_mode: str | None = None,
        use_wiki: bool = False,
        wiki_extract: str | None = None,
        wiki_bundle_id: str | None = None,
        agent_id: str | None = None,
        answer_template: str | None = None,
        stop_at_wiki_extract: bool = False,
    ) -> dict[str, Any]:
        """Run RAG or retrieval-only search for one tenant.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import VespaMcpBackend
            >>> inspect.iscoroutinefunction(VespaMcpBackend.rag_query)
            True
        """
        import os

        import httpx

        space = normalize_user_space(user_space)
        rag_url = (
            os.getenv("MCP_RAG_URL") or os.getenv("RAG_URL") or ""
        ).rstrip("/")
        mode = (search_mode or "").strip().lower() or None
        if rag_url and generate:
            payload_body: dict[str, Any] = {
                "query": query,
                "hits": hits,
                "language": language or "en",
            }
            if mode:
                payload_body["search_mode"] = mode
            if use_wiki:
                payload_body["use_wiki"] = True
            if wiki_extract:
                payload_body["wiki_extract"] = str(wiki_extract)
            if wiki_bundle_id:
                payload_body["wiki_bundle_id"] = str(wiki_bundle_id)
            if agent_id:
                payload_body["agent_id"] = str(agent_id)
            if answer_template:
                payload_body["answer_template"] = str(answer_template)
            if stop_at_wiki_extract:
                payload_body["stop_at_wiki_extract"] = True
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{rag_url}/rag/query",
                    json=payload_body,
                )
                response.raise_for_status()
                payload = response.json()
            payload["user_space"] = space
            if mode:
                payload.setdefault("search_mode", mode)
            return payload

        retrieved = await self.hybrid_search(
            query,
            hits=hits,
            user_space=space,
            language=language,
            search_mode=mode or "both",
        )
        return {
            "query": query,
            "user_space": space,
            "answer": None,
            "report_markdown": None,
            "generate": False,
            "search_mode": retrieved.get("search_mode"),
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
        """Fetch one parent document with tenant isolation checks.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import VespaMcpBackend
            >>> inspect.iscoroutinefunction(VespaMcpBackend.get_document)
            True
        """
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
        """Merge ontology payloads from retrieved documents.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import VespaMcpBackend
            >>> inspect.iscoroutinefunction(VespaMcpBackend.ontology_from_query)
            True
        """
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

    async def okf_bundle_list(self, *, user_space: str) -> dict[str, Any]:
        """List OKF bundles for the caller's tenant.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import VespaMcpBackend
            >>> inspect.iscoroutinefunction(VespaMcpBackend.okf_bundle_list)
            True
        """
        from thot.okf.store import OkfBundleStore

        space = normalize_user_space(user_space)
        store = OkfBundleStore()
        bundles = store.list_bundles(space)
        return {
            "user_space": space,
            "bundles": [b.model_dump(mode="json") for b in bundles],
        }

    async def okf_bundle_get(
        self,
        *,
        user_space: str,
        bundle_id: str,
        concept_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch OKF bundle payload for the caller's tenant.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import VespaMcpBackend
            >>> inspect.iscoroutinefunction(VespaMcpBackend.okf_bundle_get)
            True
        """
        from thot.okf.store import OkfBundleStore

        space = normalize_user_space(user_space)
        store = OkfBundleStore()
        payload = store.bundle_payload(bundle_id, space, concept_id=concept_id)
        if payload is None:
            return {
                "user_space": space,
                "bundle_id": bundle_id,
                "error": "bundle not found or access denied",
            }
        return payload

    async def workspace_wiki_list(
        self, *, user_space: str, path: str = "wiki"
    ) -> dict[str, Any]:
        """List markdown wiki files under a workspace path.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import VespaMcpBackend
            >>> inspect.iscoroutinefunction(VespaMcpBackend.workspace_wiki_list)
            True
        """
        from thot.tools.ingest.user_workspace import UserWorkspace

        space = normalize_user_space(user_space)
        ws = UserWorkspace(space)
        rel = (path or "wiki").strip().lstrip("/")
        tree = ws.list_dir(rel)
        files = [
            e
            for e in tree.get("entries") or []
            if e.get("kind") == "file"
            and str(e.get("name") or "").lower().endswith((".md", ".markdown"))
        ]
        return {
            "user_space": space,
            "path": rel,
            "files": files,
            "count": len(files),
        }

    async def workspace_wiki_get(
        self, *, user_space: str, path: str
    ) -> dict[str, Any]:
        """Read one workspace wiki markdown file.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import VespaMcpBackend
            >>> inspect.iscoroutinefunction(VespaMcpBackend.workspace_wiki_get)
            True
        """
        from thot.tools.ingest.user_workspace import UserWorkspace

        space = normalize_user_space(user_space)
        ws = UserWorkspace(space)
        rel = (path or "").strip().lstrip("/")
        if not rel:
            raise ValueError("path is required")
        try:
            full = ws.resolve_file(rel)
        except ValueError as exc:
            return {
                "user_space": space,
                "path": rel,
                "error": str(exc),
                "markdown": "",
            }
        if not full.is_file():
            return {
                "user_space": space,
                "path": rel,
                "error": "file not found",
                "markdown": "",
            }
        text = full.read_text(encoding="utf-8")
        return {
            "user_space": space,
            "path": rel,
            "markdown": text,
            "chars": len(text),
        }

    async def okf_wiki_put(
        self, *, user_space: str, bundle_id: str, markdown: str
    ) -> dict[str, Any]:
        """Write LLMWiki markdown into an OKF bundle.

        Example:
            >>> import inspect
            >>> from thot.mcp.handlers import VespaMcpBackend
            >>> inspect.iscoroutinefunction(VespaMcpBackend.okf_wiki_put)
            True
        """
        from thot.okf.store import OkfBundleStore

        space = normalize_user_space(user_space)
        store = OkfBundleStore()
        try:
            wiki_path = store.put_wiki(bundle_id, space, markdown)
        except FileNotFoundError:
            return {
                "user_space": space,
                "bundle_id": bundle_id,
                "error": "bundle not found or access denied",
            }
        except ValueError as exc:
            return {
                "user_space": space,
                "bundle_id": bundle_id,
                "error": str(exc),
            }
        return {
            "user_space": space,
            "bundle_id": bundle_id,
            "path": wiki_path,
            "chars": len(markdown or ""),
            "ok": True,
        }


class McpHandlers:
    """Dispatch MCP tools with forced ``user_space`` and metrics."""

    def __init__(self, backend: McpBackend | None = None) -> None:
        """Create handlers with an optional injectable backend.

        Example:
            >>> from thot.mcp.handlers import McpHandlers
            >>> isinstance(McpHandlers().backend, object)
            True
        """
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
            ...     async def okf_bundle_list(self, **kw):
            ...         return {"user_space": kw["user_space"], "bundles": []}
            ...     async def okf_bundle_get(self, **kw):
            ...         return {"user_space": kw["user_space"], "bundle_id": kw["bundle_id"]}
            ...     async def workspace_wiki_list(self, **kw):
            ...         return {"user_space": kw["user_space"], "files": []}
            ...     async def workspace_wiki_get(self, **kw):
            ...         return {"user_space": kw["user_space"], "markdown": ""}
            ...     async def okf_wiki_put(self, **kw):
            ...         return {"user_space": kw["user_space"], "ok": True}
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
                search_mode=args.get("search_mode"),
            )
        if tool_name == "rag_query":
            return await self.backend.rag_query(
                str(args.get("query") or ""),
                hits=int(args.get("hits") or 8),
                user_space=space,
                language=args.get("language"),
                generate=bool(args.get("generate", True)),
                search_mode=args.get("search_mode"),
                use_wiki=bool(args.get("use_wiki", False)),
                wiki_extract=args.get("wiki_extract"),
                wiki_bundle_id=args.get("wiki_bundle_id"),
                agent_id=args.get("agent_id"),
                answer_template=args.get("answer_template"),
                stop_at_wiki_extract=bool(
                    args.get("stop_at_wiki_extract", False)
                ),
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
        if tool_name == "okf_bundle_list":
            return await self.backend.okf_bundle_list(user_space=space)
        if tool_name == "okf_bundle_get":
            return await self.backend.okf_bundle_get(
                user_space=space,
                bundle_id=str(args.get("bundle_id") or ""),
                concept_id=args.get("concept_id"),
            )
        if tool_name == "workspace_wiki_list":
            return await self.backend.workspace_wiki_list(
                user_space=space,
                path=str(args.get("path") or "wiki"),
            )
        if tool_name == "workspace_wiki_get":
            return await self.backend.workspace_wiki_get(
                user_space=space,
                path=str(args.get("path") or ""),
            )
        if tool_name == "okf_wiki_put":
            return await self.backend.okf_wiki_put(
                user_space=space,
                bundle_id=str(args.get("bundle_id") or ""),
                markdown=str(args.get("markdown") or ""),
            )
        raise KeyError(f"unknown tool handler: {tool_name}")
