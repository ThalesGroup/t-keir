"""Title: Middleware

ASGI middleware for governor enforcement.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from thot import __version__ as TKEIR_VERSION
from thot.action.correlation import (
    CORRELATION_HEADER,
    TRACEPARENT_HEADER,
    correlation_from_headers,
    reset_trace_context,
    set_trace_context,
)
from thot.action.middleware import (
    _SKIP_RECORD_PATHS,
    _env_name,
    _service_name,
    intent_for_path,
    request_body_hash,
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
from thot.governor.approvals import ApprovalQueue
from thot.governor.budgets import BudgetStore
from thot.governor.config import governor_settings
from thot.governor.flags import RuntimeFlagsStore
from thot.governor.policy import PolicyEvaluator

LOGGER = logging.getLogger(__name__)

_SKIP_ENFORCE_PATHS = _SKIP_RECORD_PATHS | {
    "/docs",
    "/openapi.json",
    "/redoc",
}


def _build_blocked_record(
    request: Request,
    *,
    service: str,
    started: str,
    ended: str,
    policy,
) -> ActionRecord:
    body = b""
    ctx = correlation_from_headers(
        request.headers.get(TRACEPARENT_HEADER),
        request.headers.get(CORRELATION_HEADER),
    )
    req_hash = sha256_hex(
        f"{request.method}|{request.url.path}|{request_body_hash(body)}"
    )
    return ActionRecord(
        action_id=ctx.action_id,
        correlation_id=ctx.correlation_id,
        occurred_at=started,
        actor=ActorInfo(
            type="human" if policy.actor_id != service else "service",
            id=policy.actor_id,
        ),
        intent=IntentInfo(
            declared=intent_for_path(request.url.path),
            scope_source="oauth-scope",
        ),
        context=ActionContext(
            env=_env_name(),
            service=service,
            versions=ContextVersions(app=TKEIR_VERSION),
            request_hash=req_hash,
        ),
        decision=DecisionInfo(
            policy_result=policy.result,
            rules_fired=policy.rules_fired,
        ),
        execution=ExecutionInfo(
            started_at=started,
            ended_at=ended,
            status="blocked",
        ),
        result=ResultInfo(error=policy.message),
    )


class GovernorEnforceMiddleware(BaseHTTPMiddleware):
    """Block or escalate requests when governor mode is enforce."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        sink: ActionSink | None = None,
        service: str | None = None,
        evaluator: PolicyEvaluator | None = None,
    ) -> None:
        super().__init__(app)
        self._sink = sink if sink is not None else default_action_sink()
        self._service = service or _service_name()
        self._evaluator = evaluator
        self._evaluator_error: str | None = None

    def _get_evaluator(self) -> PolicyEvaluator:
        if self._evaluator is not None:
            return self._evaluator
        settings = governor_settings()
        try:
            flags = RuntimeFlagsStore(settings.flags_path)
            budgets = BudgetStore(settings.budget_db_path, settings)
            approvals = ApprovalQueue(settings.approvals_path)
        except OSError as exc:
            # Named volumes can be root-owned until volume-init / chown runs.
            self._evaluator_error = str(exc)
            raise RuntimeError(
                f"governor state not writable at {settings.flags_path}: {exc}"
            ) from exc
        self._evaluator = PolicyEvaluator(
            settings, flags, budgets, approvals
        )
        return self._evaluator

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        path = request.url.path
        if path in _SKIP_ENFORCE_PATHS:
            return await call_next(request)

        try:
            evaluator = self._get_evaluator()
        except RuntimeError as exc:
            LOGGER.error("Governor middleware unavailable: %s", exc)
            return Response(
                content='{"detail":"governor state unavailable"}',
                status_code=503,
                media_type="application/json",
            )
        if evaluator.mode == "off":
            return await call_next(request)

        ctx = correlation_from_headers(
            request.headers.get(TRACEPARENT_HEADER),
            request.headers.get(CORRELATION_HEADER),
        )
        token = set_trace_context(ctx)
        started = utc_now_rfc3339()

        policy = evaluator.evaluate_http(
            method=request.method,
            path=path,
            authorization=request.headers.get("authorization"),
            service=self._service,
        )
        request.state.governor_decision = policy

        if evaluator.mode == "enforce" and policy.result in {
            "deny",
            "escalate",
        }:
            ended = utc_now_rfc3339()
            if policy.result == "escalate":
                evaluator.approvals.enqueue(
                    correlation_id=ctx.correlation_id,
                    actor_id=policy.actor_id,
                    intent=policy.intent,
                    reason=policy.message,
                )
            record = _build_blocked_record(
                request,
                service=self._service,
                started=started,
                ended=ended,
                policy=policy,
            )
            record.ext["http"] = {
                "method": request.method,
                "path": path,
                "status": 403,
            }
            self._sink.append(record)
            reset_trace_context(token)
            return JSONResponse(
                status_code=403,
                content={
                    "detail": policy.message,
                    "rules": policy.rules_fired,
                },
                headers={
                    CORRELATION_HEADER: ctx.correlation_id,
                    TRACEPARENT_HEADER: ctx.traceparent(),
                },
            )

        try:
            response = await call_next(request)
        finally:
            reset_trace_context(token)

        if (
            evaluator.mode in {"observe", "enforce"}
            and policy.result == "allow"
            and response.status_code < 400
        ):
            evaluator.consume_for_intent(policy)

        if policy.budget and policy.budget.throttled:
            response.headers["X-Budget-Throttled"] = policy.budget.unit

        return response
