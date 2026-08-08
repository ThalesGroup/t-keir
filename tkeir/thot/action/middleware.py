"""Title: Middleware

FastAPI/Starlette middleware for correlation IDs and ActionRecords.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Literal

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
    "/agent/runs": "agent.run",
    "/agent/agents": "agent.read",
    "/agent/workflows": "agent.read",
}

# Keys handlers may attach via ``request.state.action_log`` (and JSON extras).
_ACTION_LOG_KEYS = (
    "agent",
    "workflow",
    "run_id",
    "spiffe_id",
    "user_space",
    "goal",
    "run_status",
    "tool",
)


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
        >>> intent_for_path("/agent/runs")
        'agent.run'
        >>> intent_for_path("/agent/runs/abc/cancel")
        'agent.cancel'
        >>> intent_for_path("/unknown")
        'search'
    """
    if path in _PATH_INTENT:
        return _PATH_INTENT[path]
    if path.startswith("/agent/"):
        if path.endswith("/publish"):
            return "agent.publish"
        if path.endswith("/cancel"):
            return "agent.cancel"
        if path.startswith("/agent/runs/"):
            return "agent.run"
        return "agent"
    return "search"


def request_body_hash(body: bytes) -> str:
    """Hash request body without retaining the plaintext.

    Example:
        >>> request_body_hash(b"{}") == sha256_hex(b"{}")
        True
    """
    return sha256_hex(body)


def _run_id_from_path(path: str) -> str | None:
    """Extract ``run_id`` from ``/agent/runs/{run_id}[/…]`` paths.

    Example:
        >>> _run_id_from_path("/agent/runs/abc/cancel")
        'abc'
        >>> _run_id_from_path("/health") is None
        True
    """
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3 and parts[0] == "agent" and parts[1] == "runs":
        return parts[2]
    return None


def _safe_json_object(body: bytes) -> dict[str, Any]:
    """Parse a JSON object body; return ``{}`` on any failure.

    Example:
        >>> _safe_json_object(b'{"a": 1}')
        {'a': 1}
        >>> _safe_json_object(b"not-json")
        {}
    """
    if not body:
        return {}
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _coerce_log_value(value: Any, *, max_len: int = 160) -> str | None:
    """Normalize a log field to a short string (or ``None`` to omit).

    Example:
        >>> _coerce_log_value(True)
        'true'
        >>> _coerce_log_value("  ") is None
        True
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _handler_action_log(request: Request) -> dict[str, str]:
    """Collect optional structured fields set by route handlers.

    Example:
        >>> from starlette.requests import Request
        >>> req = Request(
        ...     {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""}
        ... )
        >>> req.state.action_log = {"agent": "wiki"}
        >>> _handler_action_log(req)
        {'agent': 'wiki'}
    """
    raw = getattr(request.state, "action_log", None)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key in _ACTION_LOG_KEYS:
        if key not in raw:
            continue
        coerced = _coerce_log_value(
            raw[key], max_len=200 if key == "goal" else 160
        )
        if coerced is not None:
            out[key] = coerced
    return out


def _body_action_hints(path: str, body: bytes) -> dict[str, str]:
    """Best-effort agent/workflow/goal hints from a create-run JSON body.

    Example:
        >>> _body_action_hints("/agent/runs", b'{"agent": "wiki"}')
        {'agent': 'wiki'}
        >>> _body_action_hints("/health", b'{"agent": "wiki"}')
        {}
    """
    if path != "/agent/runs" or not body:
        return {}
    data = _safe_json_object(body)
    out: dict[str, str] = {}
    for key in ("agent", "workflow", "goal"):
        coerced = _coerce_log_value(
            data.get(key), max_len=200 if key == "goal" else 120
        )
        if coerced is not None:
            out[key] = coerced
    return out


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
        wall_started = time.monotonic()
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
        duration_ms = int((time.monotonic() - wall_started) * 1000)
        response.headers[CORRELATION_HEADER] = ctx.correlation_id
        response.headers[TRACEPARENT_HEADER] = ctx.traceparent()

        path = request.url.path
        method = request.method.upper()
        if path not in _SKIP_RECORD_PATHS:
            intent = intent_for_path(path)
            req_hash = sha256_hex(f"{method}|{path}|{request_body_hash(body)}")
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
            extras = _body_action_hints(path, body)
            extras.update(_handler_action_log(request))
            path_run_id = _run_id_from_path(path)
            if path_run_id and "run_id" not in extras:
                extras["run_id"] = path_run_id
            record = ActionRecord(
                action_id=ctx.action_id,
                correlation_id=ctx.correlation_id,
                occurred_at=started,
                actor=ActorInfo(type="service", id=self._service),
                intent=IntentInfo(
                    declared=intent,
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
                "method": method,
                "path": path,
                "status": status,
                "duration_ms": duration_ms,
            }
            if extras:
                record.ext["request"] = extras
            self._sink.append(record)

            detail_bits = [
                f"{method} {path}",
                f"-> {status}",
                f"({duration_ms}ms)",
                f"intent={intent}",
            ]
            for key in (
                "agent",
                "workflow",
                "run_id",
                "spiffe_id",
                "user_space",
                "run_status",
            ):
                if key in extras:
                    detail_bits.append(f"{key}={extras[key]}")
            if extras.get("goal"):
                detail_bits.append(f"goal={extras['goal']!r}")
            if error:
                detail_bits.append(f"error={error[:120]!r}")

            log_structured(
                "info",
                "request completed " + " ".join(detail_bits),
                service=self._service,
                correlation_id=ctx.correlation_id,
                action_id=ctx.action_id,
                actor=extras.get("agent") or self._service,
                http_status=status,
                path=path,
                method=method,
                intent=intent,
                duration_ms=duration_ms,
                status=exec_status,
                **extras,
            )

        reset_trace_context(token)
        return response
