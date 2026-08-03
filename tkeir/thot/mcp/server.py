"""Title: MCP HTTP server

``tkeir-mcp`` entrypoint — FastAPI HTTP + optional MCP stdio transport.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from thot import __version__ as TKEIR_VERSION
from thot.action.correlation import current_correlation_id, generate_trace_id
from thot.action.middleware import ActionCorrelationMiddleware
from thot.action.models import (
    ActionContext,
    ActionRecord,
    ActorInfo,
    ContextVersions,
    DecisionInfo,
    ExecutionInfo,
    IntentInfo,
    ResultInfo,
    sha256_hex,
    utc_now_rfc3339,
)
from thot.action.sink import default_action_sink
from thot.core.StructuredLogging import configure_json_logging, log_structured
from thot.core.ThotMetrics import ThotMetrics
from thot.mcp.authz import McpAuthError, authorize_tool
from thot.mcp.handlers import McpHandlers, VespaMcpBackend
from thot.mcp.tools_catalog import TOOLS, get_tool, tools_as_mcp_list
from thot.mcp.transport import mcp_sdk_available, run_stdio_server

LOGGER = logging.getLogger(__name__)


class ToolCallRequest(BaseModel):
    """HTTP body for ``POST /mcp/call``."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpRuntime:
    """Shared runtime for HTTP and stdio MCP transports."""

    def __init__(self) -> None:
        """Initialize handlers and default authorization from env.

        Example:
            >>> from thot.mcp.server import McpRuntime
            >>> isinstance(McpRuntime().handlers, object)
            True
        """
        self.handlers = McpHandlers(backend=VespaMcpBackend())
        self.default_authorization: str | None = os.getenv("MCP_AUTHORIZATION")

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        authorization: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Authorize, execute, and audit one tool call.

        Example:
            >>> import asyncio
            >>> from thot.mcp.server import McpRuntime
            >>> from thot.mcp.handlers import McpHandlers
            >>> from thot.mcp.authz import McpPrincipal

            >>> class _Stub:
            ...     async def hybrid_search(self, query, **kw):
            ...         return {"query": query, "user_space": kw["user_space"], "chunks": []}
            ...     async def rag_query(self, query, **kw):
            ...         return await self.hybrid_search(query, **kw)
            ...     async def get_document(self, **kw):
            ...         return {"user_space": kw["user_space"], "fields": {}}
            ...     async def ontology_from_query(self, query, **kw):
            ...         return {"user_space": kw["user_space"], "summary": ""}
            >>> rt = McpRuntime()
            >>> rt.handlers = McpHandlers(backend=_Stub())
            >>> import contextlib, io
            >>> buf = io.StringIO()
            >>> with contextlib.redirect_stdout(buf):
            ...     out = asyncio.run(rt.call_tool("search", {"query": "q"}))
            >>> out["user_space"]
            'dev@tkeir'
        """
        tool = get_tool(name)
        cid = correlation_id or current_correlation_id() or generate_trace_id()
        started = utc_now_rfc3339()
        status = "success"
        error: str | None = None
        decision = "allow"
        result: dict[str, Any] = {}
        principal_subject = "anonymous"
        principal_space = "unknown"
        principal_auth = False
        try:
            principal = authorize_tool(name, tool.intent, authorization)
            principal_subject = principal.subject
            principal_space = principal.user_space
            principal_auth = principal.auth_enabled
            result = await self.handlers.invoke(name, arguments, principal)
        except McpAuthError as exc:
            status = "blocked"
            decision = "deny"
            error = str(exc)
            raise
        except PermissionError as exc:
            status = "blocked"
            decision = "deny"
            error = str(exc)
            raise
        except Exception as exc:  # noqa: BLE001
            status = "failure"
            error = str(exc)
            LOGGER.exception("MCP tool %s failed", name)
            raise
        finally:
            ended = utc_now_rfc3339()
            record = ActionRecord(
                correlation_id=cid,
                occurred_at=started,
                actor=ActorInfo(
                    type="service",
                    id=principal_subject,
                ),
                intent=IntentInfo(
                    declared=tool.intent,
                    scope_source="oauth-scope" if principal_auth else "manual",
                ),
                context=ActionContext(
                    env=os.getenv("TKEIR_ENV", "dev"),
                    service=os.getenv("TKEIR_SERVICE", "tkeir-mcp"),
                    versions=ContextVersions(app=TKEIR_VERSION),
                    request_hash=sha256_hex(
                        f"{name}:{sorted((arguments or {}).items())}"
                    ),
                ),
                decision=DecisionInfo(
                    policy_result=decision,  # type: ignore[arg-type]
                    rules_fired=[f"mcp.tool:{name}"],
                ),
                execution=ExecutionInfo(
                    started_at=started,
                    ended_at=ended,
                    status=status,  # type: ignore[arg-type]
                ),
                result=ResultInfo(
                    output_hash=sha256_hex(str(result)[:4096]),
                    chunk_ids=[
                        str(c.get("chunk_id"))
                        for c in result.get("chunks") or []
                        if isinstance(c, dict) and c.get("chunk_id")
                    ],
                    doc_ids=[
                        str(d) for d in result.get("document_ids") or [] if d
                    ],
                    error=error,
                ),
                ext={
                    "mcp_tool": name,
                    "user_space": principal_space,
                    "action_kind": "tool.invoke",
                },
            )
            default_action_sink().append(record)
            log_structured(
                "info",
                "mcp_tool_invoke",
                service=os.getenv("TKEIR_SERVICE", "tkeir-mcp"),
                correlation_id=cid,
                action_id=record.action_id,
                actor=principal_subject,
                tool=name,
                user_space=principal_space,
                status=status,
            )
        return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: configure logging and attach :class:`McpRuntime`.

        Example:
            >>> import inspect
            >>> from thot.mcp.server import lifespan
            >>> inspect.isfunction(lifespan)
            True
    """
    configure_json_logging(service=os.getenv("TKEIR_SERVICE", "tkeir-mcp"))
    app.state.mcp = McpRuntime()
    ThotMetrics.create_counter(
        short_name="mcp_http",
        function_name="mcp_http_requests_total",
        counter_description="MCP HTTP requests",
    )
    yield


app = FastAPI(
    title="T-KEIR MCP",
    version=TKEIR_VERSION,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ActionCorrelationMiddleware)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe.

    Example:
        >>> import inspect
        >>> from thot.mcp.server import health
        >>> inspect.iscoroutinefunction(health)
        True
    """
    return {"status": "ok", "service": "tkeir-mcp"}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    """Readiness probe.

    Example:
        >>> import inspect
        >>> from thot.mcp.server import ready
        >>> inspect.iscoroutinefunction(ready)
        True
    """
    return {
        "status": "ready",
        "mcp_sdk": mcp_sdk_available(),
        "tools": [t.name for t in TOOLS],
    }


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics exposition.

    Example:
        >>> import inspect
        >>> from thot.mcp.server import metrics
        >>> inspect.iscoroutinefunction(metrics)
        True
    """
    payload = ThotMetrics.generateMetricsResponse()
    return Response(
        content=payload,
        media_type=ThotMetrics.METRIC_MIME_TYPE,
    )


@app.get("/mcp/tools")
async def list_tools() -> dict[str, Any]:
    """List MCP tools (HTTP convenience mirror of ``tools/list``).

    Example:
        >>> import inspect
        >>> from thot.mcp.server import list_tools
        >>> inspect.iscoroutinefunction(list_tools)
        True
    """
    return {"tools": tools_as_mcp_list()}


@app.post("/mcp/call")
async def call_tool_http(
    body: ToolCallRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Invoke one MCP tool over HTTP (Compose / curl friendly).

    Example:
        >>> import inspect
        >>> from thot.mcp.server import call_tool_http
        >>> inspect.iscoroutinefunction(call_tool_http)
        True
    """
    runtime: McpRuntime = request.app.state.mcp
    ThotMetrics.increment_counter(
        short_name="mcp_http",
        method="POST",
        path="/mcp/call",
        status=200,
    )
    try:
        result = await runtime.call_tool(
            body.name,
            body.arguments,
            authorization=authorization,
            correlation_id=current_correlation_id(),
        )
    except McpAuthError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=str(exc)
        ) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"name": body.name, "result": result}


def main(argv: list[str] | None = None) -> None:
    """CLI entry: ``tkeir-mcp [--stdio]`` or HTTP on ``MCP_PORT`` (default 8093).

    Example:
        >>> from thot.mcp.server import main
        >>> import inspect
        >>> inspect.isfunction(main)
        True
    """
    parser = argparse.ArgumentParser(description="T-KEIR MCP server (Phase A)")
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Serve over MCP stdio (requires mcp package)",
    )
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "0.0.0.0"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "8093")),
    )
    args = parser.parse_args(argv)

    if args.stdio:
        runtime = McpRuntime()
        asyncio.run(run_stdio_server(runtime))
        return

    import uvicorn

    uvicorn.run(
        "thot.mcp.server:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
