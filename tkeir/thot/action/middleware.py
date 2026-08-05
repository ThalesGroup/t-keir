"""Title: Middleware

FastAPI/Starlette middleware for correlation IDs and ActionRecords.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os
from typing import Callable, Literal

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from thot import __version__ as TKEIR_VERSION
from thot.action.correlation import (
    CORRELATION_HEADER,
    TRACEPARENT_HEADER,
    correlation_from_headers,
    reset_trace_context,
    set_trace_context,
)
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
from thot.action.sink import ActionSink, default_action_sink
from thot.core.StructuredLogging import log_structured

_SKIP_RECORD_PATHS = frozenset({"/health", "/ready", "/metrics"})

_PATH_INTENT = {
    "/rag/query": "search",
    "/search": "search",
    "/ingest/document": "ingest",
    "/ingest/batch": "ingest",
    "/collect": "collect",
    "/collect/batch": "collect",
    "/topics": "collect.read",
    "/dedupe": "collect.read",
    "/audit/actions": "audit.read",
    "/audit/report": "audit.read",
    "/audit/verify": "audit.read",
    "/audit/archive": "audit.read",
    "/okf/export": "okf.export",
}


def _env_name() -> str:
    """Return deployment environment name from env vars.

    Example:
        >>> isinstance(_env_name(), str) and len(_env_name()) > 0
        True
    """
    return os.getenv("TKEIR_ENV", os.getenv("ENVIRONMENT", "dev"))


def _service_name() -> str:
    """Return service name stamped on ActionRecords.

    Example:
        >>> isinstance(_service_name(), str) and len(_service_name()) > 0
        True
    """
    return os.getenv("TKEIR_SERVICE", "tkeir-api")


def intent_for_path(path: str) -> str:
    """Map an HTTP path to a declared action intent.

    Example:
        >>> intent_for_path("/rag/query")
        'search'
        >>> intent_for_path("/collect")
        'collect'
        >>> intent_for_path("/unknown")
        'search'
    """
    return _PATH_INTENT.get(path, "search")


def request_body_hash(body: bytes) -> str:
    """Hash request body without retaining the plaintext.

    Example:
        >>> request_body_hash(b"{}") == sha256_hex(b"{}")
        True
    """
    return sha256_hex(body)


class ActionCorrelationMiddleware(BaseHTTPMiddleware):
    """Propagate correlation IDs and emit observe-mode ActionRecords."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        sink: ActionSink | None = None,
        service: str | None = None,
    ) -> None:
        """Wire middleware with an optional ActionRecord sink.

        Args:
            app: Downstream ASGI app.
            sink: Observe sink; defaults to the process in-memory sink.
            service: Service name stamped on ActionRecords.

        Example:
            >>> from starlette.applications import Starlette
            >>> mid = ActionCorrelationMiddleware(Starlette())
            >>> mid._service.endswith("api") or mid._service == "tkeir-api"
            True
        """
        super().__init__(app)
        self._sink = sink if sink is not None else default_action_sink()
        self._service = service or _service_name()

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Handle one request: bind context, call next, emit record.

        Example:
            >>> isinstance(ActionCorrelationMiddleware, type)
            True
        """
        ctx = correlation_from_headers(
            request.headers.get(TRACEPARENT_HEADER),
            request.headers.get(CORRELATION_HEADER),
        )
        token = set_trace_context(ctx)
        started = utc_now_rfc3339()
        body = await request.body()

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(request.scope, receive)
        status = 500
        error: str | None = None
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as exc:
            error = str(exc)
            reset_trace_context(token)
            raise
        ended = utc_now_rfc3339()
        response.headers[CORRELATION_HEADER] = ctx.correlation_id
        response.headers[TRACEPARENT_HEADER] = ctx.traceparent()

        path = request.url.path
        if path not in _SKIP_RECORD_PATHS:
            req_hash = sha256_hex(
                f"{request.method}|{path}|{request_body_hash(body)}"
            )
            ExecStatus = Literal[
                "success",
                "failure",
                "blocked",
                "rolled_back",
            ]
            exec_status: ExecStatus = "success" if status < 400 else "failure"
            governor_decision = getattr(
                request.state, "governor_decision", None
            )
            decision = DecisionInfo()
            if governor_decision is not None:
                decision = DecisionInfo(
                    policy_result=governor_decision.result,
                    rules_fired=governor_decision.rules_fired,
                )
                if governor_decision.result != "allow":
                    exec_status = "blocked"
            record = ActionRecord(
                action_id=ctx.action_id,
                correlation_id=ctx.correlation_id,
                occurred_at=started,
                actor=ActorInfo(type="service", id=self._service),
                intent=IntentInfo(
                    declared=intent_for_path(path),
                    scope_source="manual",
                ),
                context=ActionContext(
                    env=_env_name(),
                    service=self._service,
                    versions=ContextVersions(app=TKEIR_VERSION),
                    request_hash=req_hash,
                ),
                decision=decision,
                execution=ExecutionInfo(
                    started_at=started,
                    ended_at=ended,
                    status=exec_status,
                ),
                result=ResultInfo(error=error),
            )
            record.ext["http"] = {
                "method": request.method,
                "path": path,
                "status": status,
            }
            self._sink.append(record)
            log_structured(
                "info",
                "request completed",
                service=self._service,
                correlation_id=ctx.correlation_id,
                action_id=ctx.action_id,
                actor=self._service,
                http_status=status,
                path=path,
            )

        reset_trace_context(token)
        return response
