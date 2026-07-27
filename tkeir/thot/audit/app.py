"""Title: Audit FastAPI application

Audit API service (``tkeir-audit``).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from thot import __version__ as TKEIR_VERSION
from thot.action.middleware import ActionCorrelationMiddleware
from thot.audit.archiver import archive_unarchived
from thot.audit.auth import require_audit_auth
from thot.audit.config import audit_settings
from thot.audit.hot_store import HotStore, open_hot_store
from thot.audit.privacy import SubjectKeyStore
from thot.audit.report import load_report, render_html
from thot.audit.verify import verify_store
from thot.audit.worm_store import WormSegmentStore
from thot.core.StructuredLogging import configure_json_logging
from thot.core.ThotMetrics import ThotMetrics

LOGGER = logging.getLogger(__name__)


class AppState:
    """Shared audit runtime."""

    def __init__(self) -> None:
        settings = audit_settings()
        self.settings = settings
        self.hot: HotStore | None = open_hot_store(settings.hot_store_url)
        self.worm = WormSegmentStore(settings.worm_root)
        self.keys = SubjectKeyStore(settings.subject_keys_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_json_logging(service=os.getenv("TKEIR_SERVICE", "tkeir-audit"))
    app.state.audit = AppState()
    try:
        yield
    finally:
        state: AppState = app.state.audit
        if state.hot is not None:
            state.hot.close()
        state.keys.close()


app = FastAPI(title="T-KEIR Audit", version=TKEIR_VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "AUDIT_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    ActionCorrelationMiddleware,
    service=os.getenv("TKEIR_SERVICE", "tkeir-audit"),
)


class ActionsResponse(BaseModel):
    total: int
    items: list[dict[str, Any]] = Field(default_factory=list)


@app.get("/health")
async def health() -> dict[str, str]:
    state: AppState = app.state.audit
    if state.hot is None:
        raise HTTPException(status_code=503, detail="Hot store unavailable")
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    state: AppState = app.state.audit
    if state.hot is None:
        raise HTTPException(status_code=503, detail="Hot store unavailable")
    return {"status": "ready"}


@app.get("/metrics")
async def metrics() -> Response:
    ThotMetrics.create_counter(
        short_name="audit_http",
        function_name="tkeir_audit_http_requests_total",
        counter_description="Audit HTTP requests observed",
    )
    payload = ThotMetrics.generateMetricsResponse()
    return Response(
        content=payload,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/audit/actions", response_model=ActionsResponse)
async def list_actions(
    correlation_id: str | None = None,
    actor: str | None = None,
    occurred_from: str | None = Query(default=None, alias="from"),
    occurred_to: str | None = Query(default=None, alias="to"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _actor: str = Depends(require_audit_auth),
) -> ActionsResponse:
    state: AppState = app.state.audit
    if state.hot is None:
        raise HTTPException(status_code=503, detail="Hot store unavailable")
    records = state.hot.query(
        correlation_id=correlation_id,
        actor_id=actor,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        limit=limit,
        offset=offset,
    )
    return ActionsResponse(
        total=state.hot.count(),
        items=[
            record.model_dump(by_alias=True, mode="json") for record in records
        ],
    )


@app.get("/audit/report")
async def audit_report(
    correlation_id: str,
    format: str = Query(default="json", pattern="^(json|html)$"),
    _actor: str = Depends(require_audit_auth),
):
    state: AppState = app.state.audit
    if state.hot is None:
        raise HTTPException(status_code=503, detail="Hot store unavailable")
    report = load_report(state.hot, correlation_id)
    if format == "html":
        return HTMLResponse(render_html(report))
    return report


@app.post("/audit/archive")
async def trigger_archive(
    _actor: str = Depends(require_audit_auth),
) -> dict[str, str | None]:
    state: AppState = app.state.audit
    if state.hot is None:
        raise HTTPException(status_code=503, detail="Hot store unavailable")
    segment_id = archive_unarchived(state.hot, state.worm)
    return {"segment_id": segment_id}


@app.get("/audit/verify")
async def audit_verify(
    _actor: str = Depends(require_audit_auth),
) -> dict[str, Any]:
    state: AppState = app.state.audit
    if state.hot is None:
        raise HTTPException(status_code=503, detail="Hot store unavailable")
    report = verify_store(state.hot, state.worm)
    return {
        "ok": report.ok,
        "records_checked": report.records_checked,
        "worm_segments_checked": report.worm_segments_checked,
        "errors": report.errors,
    }


def main() -> None:
    """CLI entry: server or maintenance subcommands."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in {
        "report",
        "summary",
        "verify",
        "archive",
        "forget",
        "incident",
    }:
        from thot.audit.cli import main as cli_main

        cli_main()
        return

    import uvicorn

    settings = audit_settings()
    from thot.core.StructuredLogging import configure_text_logging
    configure_text_logging(level=logging.INFO, force=True)
    uvicorn.run(
        "thot.audit.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
