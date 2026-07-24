"""Title: tkeir-okf FastAPI service (:8094).

OKF bundle export / browse / download / DSR delete.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from thot import __version__ as TKEIR_VERSION
from thot.action.middleware import ActionCorrelationMiddleware
from thot.action.models import (
    ActionContext,
    ActionRecord,
    ActorInfo,
    ContextVersions,
    DecisionInfo,
    ExecutionInfo,
    ImpactInfo,
    IntentInfo,
    ResultInfo,
    sha256_hex,
    utc_now_rfc3339,
)
from thot.action.sink import default_action_sink
from thot.core.StructuredLogging import configure_json_logging
from thot.core.ThotMetrics import ThotMetrics
from thot.governor.wiring import wire_governor_middleware
from thot.okf.exporter import export_full, export_scoped, tar_bundle
from thot.okf.models import OkfExportRequest, OkfExportResult, OkfHttpExportBody
from thot.okf.store import OkfBundleStore
from thot.tools.search.user_space import resolve_vespa_user_space

LOGGER = logging.getLogger(__name__)


class AppState:
    def __init__(self) -> None:
        self.store = OkfBundleStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_json_logging(service=os.getenv("TKEIR_SERVICE", "tkeir-okf"))
    app.state.okf = AppState()
    ThotMetrics.create_counter(
        short_name="okf_http",
        function_name="okf_http_requests_total",
        counter_description="OKF HTTP requests",
    )
    yield


app = FastAPI(
    title="T-KEIR OKF",
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
app.add_middleware(ActionCorrelationMiddleware, service="tkeir-okf")
wire_governor_middleware(app, service="tkeir-okf")


def _space(authorization: str | None) -> str:
    return resolve_vespa_user_space(authorization)


def _store(request_app: FastAPI) -> OkfBundleStore:
    return request_app.state.okf.store


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "tkeir-okf"}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    root = _store(app).root
    return {
        "status": "ready",
        "okf_root": str(root),
        "writable": os.access(root, os.W_OK),
    }


@app.get("/metrics")
async def metrics() -> Response:
    return Response(
        content=ThotMetrics.generateMetricsResponse(),
        media_type="text/plain; version=0.0.4",
    )


@app.post("/okf/export", response_model=OkfExportResult)
async def okf_export(
    body: OkfHttpExportBody,
    authorization: str | None = Header(default=None),
) -> OkfExportResult:
    """Start an OKF export. ``user_space`` always comes from auth."""
    ThotMetrics.increment_counter(
        short_name="okf_http",
        method="POST",
        path="/okf/export",
        status=200,
    )
    space = _space(authorization)
    request = OkfExportRequest(
        user_space=space,
        query=body.query,
        max_docs=body.max_docs,
        output_dir=body.output_dir,
        doc_ids=None,
    )
    if request.query:
        return await export_scoped(request)
    return await export_full(request)


@app.get("/okf/bundles")
async def okf_bundles(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    space = _space(authorization)
    bundles = _store(app).list_bundles(space)
    return {
        "user_space": space,
        "bundles": [b.model_dump(mode="json") for b in bundles],
    }


@app.get("/okf/bundles/{bundle_id}")
async def okf_bundle_get(
    bundle_id: str,
    concept_id: str | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    space = _space(authorization)
    payload = _store(app).bundle_payload(
        bundle_id, space, concept_id=concept_id
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="bundle not found")
    return payload


@app.get("/okf/bundles/{bundle_id}/download")
async def okf_bundle_download(
    bundle_id: str,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> FileResponse:
    space = _space(authorization)
    bundle = _store(app).get_bundle(bundle_id, space)
    if bundle is None:
        raise HTTPException(status_code=404, detail="bundle not found")
    tmp = Path(tempfile.mkdtemp(prefix="okf-")) / f"{bundle_id}.tar.gz"
    archive = tar_bundle(Path(bundle.path), dest=tmp)

    def _cleanup() -> None:
        try:
            archive.unlink(missing_ok=True)
            archive.parent.rmdir()
        except OSError:
            pass

    background_tasks.add_task(_cleanup)
    return FileResponse(
        path=archive,
        filename=f"{bundle_id}.tar.gz",
        media_type="application/gzip",
    )


@app.delete("/okf/bundles/{bundle_id}")
async def okf_bundle_delete(
    bundle_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """DSR / forget: log deletion ActionRecord and remove the bundle."""
    space = _space(authorization)
    store = _store(app)
    bundle = store.get_bundle(bundle_id, space)
    if bundle is None:
        raise HTTPException(status_code=404, detail="bundle not found")
    record = ActionRecord(
        correlation_id=sha256_hex(bundle_id)[:32],
        actor=ActorInfo(type="service", id=space),
        intent=IntentInfo(declared="delete", scope_source="manual"),
        context=ActionContext(
            env=os.getenv("TKEIR_ENV", "dev"),
            service="tkeir-okf",
            versions=ContextVersions(app=TKEIR_VERSION),
            request_hash=sha256_hex(f"okf.delete:{bundle_id}"),
        ),
        decision=DecisionInfo(policy_result="allow", rules_fired=["okf.dsr"]),
        execution=ExecutionInfo(
            started_at=utc_now_rfc3339(),
            ended_at=utc_now_rfc3339(),
            status="success",
        ),
        result=ResultInfo(doc_ids=[bundle_id]),
        impact=ImpactInfo(class_="destructive"),
        ext={
            "action_kind": "okf.export.delete",
            "bundle_id": bundle_id,
            "user_space": space,
        },
    )
    default_action_sink().append(record)
    ok = store.delete(bundle_id, space)
    return {
        "deleted": ok,
        "bundle_id": bundle_id,
        "action_record_id": record.action_id,
    }


def main(argv: list[str] | None = None) -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(prog="tkeir-okf")
    parser.add_argument("--host", default=os.getenv("OKF_HOST", "0.0.0.0"))
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("OKF_PORT", "8094"))
    )
    args = parser.parse_args(argv)
    import uvicorn

    uvicorn.run(
        "thot.okf.server:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
