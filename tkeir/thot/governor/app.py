"""Title: Governor FastAPI application

Governor API service (``tkeir-governor``).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from thot import __version__ as TKEIR_VERSION
from thot.action.middleware import ActionCorrelationMiddleware
from thot.core.StructuredLogging import configure_json_logging
from thot.core.ThotMetrics import ThotMetrics
from thot.governor.approvals import ApprovalQueue
from thot.governor.auth import require_admin_auth
from thot.governor.budgets import BudgetStore
from thot.governor.config import governor_settings
from thot.governor.flags import RuntimeFlagsStore
from thot.governor.models import (
    ApprovalDecision,
    ApprovalItem,
    BudgetSnapshot,
    KillRequest,
    MintTokenRequest,
    RevokeTokenRequest,
    RollbackRequest,
    RuntimeFlags,
)
from thot.governor.policy import PolicyEvaluator
from thot.governor.tokens import ActionTokenService

LOGGER = logging.getLogger(__name__)


class AppState:
    """Shared governor runtime."""

    def __init__(self) -> None:
        settings = governor_settings()
        self.settings = settings
        self.flags = RuntimeFlagsStore(settings.flags_path)
        self.budgets = BudgetStore(settings.budget_db_path, settings)
        self.approvals = ApprovalQueue(settings.approvals_path)
        self.tokens = ActionTokenService(
            revoke_path=settings.flags_path.parent / "revoked.json",
        )
        self.evaluator = PolicyEvaluator(
            settings,
            self.flags,
            self.budgets,
            self.approvals,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_json_logging(
        service=os.getenv("TKEIR_SERVICE", "tkeir-governor")
    )
    app.state.governor = AppState()
    try:
        yield
    finally:
        state: AppState = app.state.governor
        state.budgets.close()


app = FastAPI(
    title="T-KEIR Governor", version=TKEIR_VERSION, lifespan=lifespan
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "GOVERNOR_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    ActionCorrelationMiddleware,
    service=os.getenv("TKEIR_SERVICE", "tkeir-governor"),
)


class BudgetListResponse(BaseModel):
    items: list[BudgetSnapshot] = Field(default_factory=list)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    state: AppState = app.state.governor
    _ = state.flags.snapshot()
    return {"status": "ready", "mode": state.settings.mode}


@app.get("/metrics")
async def metrics() -> Response:
    ThotMetrics.create_counter(
        short_name="governor_http",
        function_name="tkeir_governor_http_requests_total",
        counter_description="Governor HTTP requests observed",
    )
    payload = ThotMetrics.generateMetricsResponse()
    return Response(
        content=payload,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/governor/flags", response_model=RuntimeFlags)
async def get_flags() -> RuntimeFlags:
    state: AppState = app.state.governor
    return state.flags.snapshot()


@app.post("/governor/kill", response_model=RuntimeFlags)
async def set_kill(
    body: KillRequest,
    actor: str = Depends(require_admin_auth),
) -> RuntimeFlags:
    state: AppState = app.state.governor
    return state.flags.set_kill(
        body.scope,
        active=body.active,
        reason=body.reason,
        actor=actor,
    )


@app.post("/governor/rollback")
async def rollback(
    body: RollbackRequest,
    actor: str = Depends(require_admin_auth),
) -> dict[str, str]:
    """Register a compensation plan and request indexer undo by run id."""
    state: AppState = app.state.governor
    run_id = (body.run_id or "").strip()
    LOGGER.info(
        "rollback requested by %s run_id=%s reason=%s",
        actor,
        run_id,
        body.reason,
    )
    # Persist a marker next to runtime flags so workers/indexers can poll it.
    marker = state.settings.flags_path.parent / "rollback-requests.jsonl"
    marker.parent.mkdir(parents=True, exist_ok=True)
    import json

    from thot.action.models import utc_now_rfc3339

    with marker.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "run_id": run_id,
                    "reason": body.reason,
                    "actor": actor,
                    "requested_at": utc_now_rfc3339(),
                    "status": "accepted",
                }
            )
            + "\n"
        )
    return {
        "status": "accepted",
        "run_id": run_id,
        "message": (
            "rollback request recorded; indexer workers poll rollback-requests.jsonl"
        ),
    }


@app.post("/governor/token")
async def mint_token(
    body: MintTokenRequest,
    actor: str = Depends(require_admin_auth),
) -> dict[str, Any]:
    """Mint a constrained action token (TTL ≤ 300s)."""
    state: AppState = app.state.governor
    compact, token = state.tokens.mint(
        actor_id=actor,
        intent=body.intent,
        audience=body.audience,
        max_budget=body.max_budget,
        constraints=dict(body.constraints),
        ttl=body.ttl,
    )
    return {
        "token": compact,
        "jti": token.jti,
        "expires_at": token.expires_at,
        "intent": token.intent,
        "delegation_note": (
            "Exchange a Keycloak access token for this constrained token "
            "(RFC 8693) in production IdP configurations."
        ),
    }


@app.post("/governor/revoke")
async def revoke_token(
    body: RevokeTokenRequest,
    actor: str = Depends(require_admin_auth),
) -> dict[str, Any]:
    """Revoke an action token by jti and/or actor (effective immediately)."""
    if not body.jti and not body.actor_id:
        raise HTTPException(status_code=400, detail="jti or actor_id required")
    state: AppState = app.state.governor
    revoked = state.tokens.revoke(jti=body.jti, actor_id=body.actor_id)
    LOGGER.info(
        "token revoke by %s reason=%s revoked=%s",
        actor,
        body.reason,
        revoked,
    )
    return {"status": "revoked", "revoked": revoked, "by": actor}


@app.get("/governor/budgets", response_model=BudgetListResponse)
async def list_budgets(
    actor: str | None = None,
    _admin: str = Depends(require_admin_auth),
) -> BudgetListResponse:
    state: AppState = app.state.governor
    subject = actor or "anonymous"
    docs = state.budgets.snapshot(
        subject,
        "docs",
        limit=state.settings.default_doc_budget,
    )
    tokens = state.budgets.snapshot(
        subject,
        "llm_tokens",
        limit=state.settings.default_llm_token_budget,
    )
    return BudgetListResponse(items=[docs, tokens])


@app.get("/governor/approvals", response_model=list[ApprovalItem])
async def list_approvals(
    _admin: str = Depends(require_admin_auth),
) -> list[ApprovalItem]:
    state: AppState = app.state.governor
    return state.approvals.list_all()


@app.post("/governor/approvals/{approval_id}/approve")
async def approve_item(
    approval_id: str,
    body: ApprovalDecision,
    actor: str = Depends(require_admin_auth),
) -> dict[str, Any]:
    state: AppState = app.state.governor
    item = state.approvals.decide(approval_id, status="approved")
    if item is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return {"status": "approved", "approval_id": approval_id, "by": actor}


@app.post("/governor/approvals/{approval_id}/deny")
async def deny_item(
    approval_id: str,
    body: ApprovalDecision,
    actor: str = Depends(require_admin_auth),
) -> dict[str, Any]:
    state: AppState = app.state.governor
    item = state.approvals.decide(approval_id, status="denied")
    if item is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return {"status": "denied", "approval_id": approval_id, "by": actor}


def main() -> None:
    """CLI entry: server or maintenance subcommands."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in {"flags", "kill", "budgets"}:
        from thot.governor.cli import main as cli_main

        cli_main()
        return

    import uvicorn

    settings = governor_settings()
    from thot.core.StructuredLogging import configure_text_logging
    configure_text_logging(level=logging.INFO, force=True)
    uvicorn.run(
        "thot.governor.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
