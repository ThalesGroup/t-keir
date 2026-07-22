"""Title: Ingest FastAPI application

FastAPI ingest service (``tkeir-ingest``).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from thot import __version__ as TKEIR_VERSION
from thot.action.correlation import current_correlation_id
from thot.action.middleware import ActionCorrelationMiddleware
from thot.action.models import new_action_id, utc_now_rfc3339
from thot.action.readiness import readiness_report
from thot.core.StructuredLogging import configure_json_logging
from thot.core.ThotMetrics import ThotMetrics
from thot.governor.wiring import wire_governor_middleware
from thot.ingest.auth import require_ingest_auth
from thot.ingest.config import ingest_settings
from thot.ingest.models import (
    BatchAcceptedResponse,
    BatchIngestRequest,
    DocumentIngestRequest,
    IngestAcceptedResponse,
    IngestJob,
    IngestJobStatus,
    IngestStatusResponse,
)
from thot.ingest.store import IngestStore
from thot.ingest.worker import IngestWorker
from thot.tools.search.vespa_client import VespaClient

LOGGER = logging.getLogger(__name__)


class AppState:
    """Shared ingest runtime state."""

    def __init__(self) -> None:
        settings = ingest_settings()
        self.settings = settings
        self.store = IngestStore(settings.root)
        self.worker = IngestWorker(self.store, settings=settings)
        self.vespa: VespaClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize store layout and optional Vespa client."""
    configure_json_logging(service=os.getenv("TKEIR_SERVICE", "tkeir-ingest"))
    app.state.ingest = AppState()
    state: AppState = app.state.ingest
    state.store.ensure_layout()
    state.vespa = VespaClient()
    try:
        yield
    finally:
        if state.vespa is not None:
            await state.vespa.aclose()


app = FastAPI(
    title="T-KEIR Ingest",
    version=TKEIR_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "INGEST_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    ActionCorrelationMiddleware,
    service=os.getenv("TKEIR_SERVICE", "tkeir-ingest"),
)
wire_governor_middleware(
    app, service=os.getenv("TKEIR_SERVICE", "tkeir-ingest")
)


def _correlation_id() -> str:
    return current_correlation_id() or new_action_id()


def _parse_json_object_field(raw: Any, *, field_name: str) -> dict[str, Any] | None:
    """Parse an optional multipart JSON object field."""
    if raw is None or hasattr(raw, "read"):
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name} JSON: {exc}",
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be a JSON object",
        )
    return parsed


def _parse_ontology_paths_field(raw: Any) -> None:
    """Reject path-only ``ontologies`` form fields (content must be uploaded)."""
    if raw is None or hasattr(raw, "read"):
        return
    text = str(raw).strip()
    if not text:
        return
    raise HTTPException(
        status_code=400,
        detail=(
            "Form field 'ontologies' as paths is not accepted: the ingest "
            "server cannot read client files. Upload each ontology with "
            "multipart field 'ontology_file' (repeatable) containing the "
            "file bytes, or use JSON ontologies[].content_base64."
        ),
    )


async def _stage_uploaded_ontologies(
    form: Any,
    staging_dir: Path,
) -> list[str]:
    """Persist multipart ontology file uploads and return staged absolute paths."""
    from thot.ingest.ontology_upload import stage_ontology_bytes

    items: list[tuple[str, bytes]] = []
    getters: list[Any] = []
    if hasattr(form, "getlist"):
        for key in ("ontology_file", "ontology_files"):
            getters.extend(list(form.getlist(key)))
    for key in ("ontology_file", "ontology_files"):
        item = form.get(key)
        if item is not None and item not in getters:
            getters.append(item)
    for upload in getters:
        if not hasattr(upload, "read"):
            continue
        upload_obj = cast(Any, upload)
        content = await upload_obj.read()
        if not content:
            continue
        name = getattr(upload_obj, "filename", None) or "ontology.ttl"
        items.append((str(name), content))
    return stage_ontology_bytes(staging_dir, items)


async def _document_extras_from_multipart(
    form: Any,
    *,
    ingest_id: str,
) -> dict[str, Any] | None:
    """Build pipeline extras from multipart metadata + uploaded ontology bytes."""
    from thot.ingest.ontology_upload import strip_client_ontology_paths
    from thot.ingest.worker import document_extras_from_metadata

    # Reject path-only ontology lists (client/server separation).
    _parse_ontology_paths_field(form.get("ontologies"))

    metadata = _parse_json_object_field(form.get("metadata"), field_name="metadata")
    metadata = strip_client_ontology_paths(metadata)
    state: AppState = app.state.ingest
    upload_dir = Path(state.settings.root) / "uploaded_ontologies" / ingest_id
    uploaded = await _stage_uploaded_ontologies(form, upload_dir)
    return document_extras_from_metadata(
        metadata,
        ontologies=uploaded or None,
    )


def _queue_job(
    *,
    source_uri: str,
    content: bytes | None,
    filename: str | None,
    content_type: str | None,
    batch_id: str | None,
    background: BackgroundTasks,
    user_space: str,
    document_extras: dict[str, Any] | None = None,
) -> IngestAcceptedResponse:
    state: AppState = app.state.ingest
    ingest_id = new_action_id()
    correlation_id = _correlation_id()
    now = utc_now_rfc3339()
    job = IngestJob(
        ingest_id=ingest_id,
        correlation_id=correlation_id,
        status=IngestJobStatus.PENDING,
        batch_id=batch_id,
        created_at=now,
        updated_at=now,
        user_space=user_space,
    )
    state.store.write_job(job)

    async def _run() -> None:
        await state.worker.process_source(
            ingest_id=ingest_id,
            correlation_id=correlation_id,
            source_uri=source_uri,
            content=content,
            filename=filename,
            content_type=content_type,
            batch_id=batch_id,
            user_space=user_space,
            document_extras=document_extras,
        )

    background.add_task(_run)
    return IngestAcceptedResponse(
        ingest_id=ingest_id,
        correlation_id=correlation_id,
        status=IngestJobStatus.PENDING,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe (process up). Use ``/ready`` for Vespa + deps."""
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    """Readiness probe: Vespa + embedding provider."""
    state: AppState = app.state.ingest
    vespa_ok = False
    if state.vespa is not None:
        vespa_ok = await state.vespa.health()
    report = await readiness_report(vespa_ok=vespa_ok)
    if report["status"] != "ready":
        raise HTTPException(status_code=503, detail=report)
    return report


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus exposition."""
    ThotMetrics.create_counter(
        short_name="ingest_http",
        function_name="tkeir_ingest_http_requests_total",
        counter_description="Ingest HTTP requests observed",
    )
    payload = ThotMetrics.generateMetricsResponse()
    return Response(
        content=payload,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.post(
    "/ingest/document",
    response_model=IngestAcceptedResponse,
    status_code=202,
)
async def ingest_document(
    request: Request,
    background: BackgroundTasks,
    actor: str = Depends(require_ingest_auth),
) -> IngestAcceptedResponse:
    """Ingest one document from multipart upload or JSON URL.

    Per-document external ontologies must be **uploaded as content** (the
    server has no access to client filesystem paths):

    - multipart: repeatable ``ontology_file`` parts (OWL/TTL/RDF bytes), and/or
    - JSON body: ``ontologies: [{filename, content_base64}, ...]``.

    Staged paths under ``INGEST_ROOT`` are passed to NER, syntax, and
    document-ontology for that document only.
    """
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/"):
        form = await request.form()
        upload = form.get("file")
        if upload is None:
            raise HTTPException(status_code=400, detail="Missing file field")
        # FastAPI/Starlette may return different concrete upload classes depending
        # on multipart parsing backend; accept anything with the upload-like API.
        if not hasattr(upload, "read"):
            raise HTTPException(status_code=400, detail="Invalid upload type")
        upload_obj = cast(Any, upload)
        content = await upload_obj.read()
        filename = getattr(upload_obj, "filename", None) or "upload.bin"
        doc_id_hint = new_action_id()
        source_uri = f"upload://{doc_id_hint}/{filename}"
        extras = await _document_extras_from_multipart(
            form, ingest_id=doc_id_hint
        )
        return _queue_job(
            source_uri=source_uri,
            content=content,
            filename=filename,
            content_type=getattr(upload_obj, "content_type", None),
            batch_id=None,
            background=background,
            user_space=actor,
            document_extras=extras,
        )
    try:
        body = DocumentIngestRequest.model_validate(await request.json())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    from thot.ingest.ontology_upload import (
        decode_ontology_uploads,
        stage_ontology_bytes,
        strip_client_ontology_paths,
    )
    from thot.ingest.worker import document_extras_from_metadata

    state: AppState = app.state.ingest
    staging_id = new_action_id()
    try:
        uploads = decode_ontology_uploads(
            [item.model_dump() for item in (body.ontologies or [])]
            if body.ontologies
            else None
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    staged: list[str] = []
    if uploads:
        staged = stage_ontology_bytes(
            Path(state.settings.root) / "uploaded_ontologies" / staging_id,
            uploads,
        )
    extras = document_extras_from_metadata(
        strip_client_ontology_paths(body.metadata),
        ontologies=staged or None,
    )
    return _queue_job(
        source_uri=str(body.url),
        content=None,
        filename=body.filename,
        content_type=None,
        batch_id=None,
        background=background,
        user_space=actor,
        document_extras=extras,
    )


@app.post(
    "/ingest/batch",
    response_model=BatchAcceptedResponse,
    status_code=202,
)
async def ingest_batch(
    request: BatchIngestRequest,
    background: BackgroundTasks,
    actor: str = Depends(require_ingest_auth),
) -> BatchAcceptedResponse:
    """Queue a batch of URL-based ingest jobs (each item may carry ontologies)."""
    from thot.ingest.ontology_upload import (
        decode_ontology_uploads,
        stage_ontology_bytes,
        strip_client_ontology_paths,
    )
    from thot.ingest.worker import document_extras_from_metadata

    state: AppState = app.state.ingest
    batch_id = new_action_id()
    correlation_id = _correlation_id()
    jobs: list[IngestAcceptedResponse] = []
    for item in request.items:
        staging_id = new_action_id()
        try:
            uploads = decode_ontology_uploads(
                [o.model_dump() for o in (item.ontologies or [])]
                if item.ontologies
                else None
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        staged: list[str] = []
        if uploads:
            staged = stage_ontology_bytes(
                Path(state.settings.root) / "uploaded_ontologies" / staging_id,
                uploads,
            )
        extras = document_extras_from_metadata(
            strip_client_ontology_paths(item.metadata),
            ontologies=staged or None,
        )
        accepted = _queue_job(
            source_uri=str(item.url),
            content=None,
            filename=item.filename,
            content_type=None,
            batch_id=batch_id,
            background=background,
            user_space=actor,
            document_extras=extras,
        )
        jobs.append(accepted)
    return BatchAcceptedResponse(
        batch_id=batch_id,
        correlation_id=correlation_id,
        jobs=jobs,
    )


@app.get("/ingest/status/{ingest_id}", response_model=IngestStatusResponse)
async def ingest_status(
    ingest_id: str,
    _actor: str = Depends(require_ingest_auth),
) -> IngestStatusResponse:
    """Return job status and manifest when available."""
    state: AppState = app.state.ingest
    job = state.store.read_job(ingest_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown ingest id")
    manifest = None
    if job.doc_id:
        manifest = state.store.read_manifest(job.doc_id)
    return IngestStatusResponse(
        ingest_id=job.ingest_id,
        correlation_id=job.correlation_id,
        status=job.status,
        doc_id=job.doc_id,
        batch_id=job.batch_id,
        manifest_path=job.manifest_path,
        error=job.error,
        noop=job.noop,
        manifest=manifest,
    )


@app.post("/ingest/stop")
async def ingest_stop(
    request: Request,
    _actor: str = Depends(require_ingest_auth),
) -> dict[str, str]:
    """Stop the ingest server process (used by client ``--stop-on-failed``)."""
    import threading

    from thot.ingest.shutdown import request_ingest_shutdown

    try:
        body = await request.json()
    except Exception:
        body = {}
    reason = "client requested /ingest/stop"
    if isinstance(body, dict) and body.get("reason"):
        reason = str(body["reason"])

    def _stop() -> None:
        request_ingest_shutdown(reason)

    # Delay so the HTTP 200 reaches the client before SIGTERM.
    threading.Timer(0.2, _stop).start()
    return {"status": "stopping", "reason": reason}


def main() -> None:
    """CLI entry point for the ingest FastAPI server or maintenance CLI."""
    import sys

    import uvicorn

    if len(sys.argv) > 1 and sys.argv[1] == "retry":
        from thot.ingest.cli import main as cli_main

        cli_main()
        return

    settings = ingest_settings()
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        "thot.ingest.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
