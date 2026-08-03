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
    Header,
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
from thot.tools.ingest.auth import (
    require_admin_ingest,
    require_ingest_auth,
    resolve_allowed_index_target,
)
from thot.tools.ingest.config import ingest_settings
from thot.tools.ingest.models import (
    BatchAcceptedResponse,
    BatchIngestRequest,
    DocumentIngestRequest,
    IngestAcceptedResponse,
    IngestJob,
    IngestJobStatus,
    IngestStatusResponse,
    JsonRecordsAcceptedResponse,
    JsonRecordsIngestRequest,
)
from thot.tools.ingest.store import IngestStore
from thot.tools.ingest.user_workspace import (
    UserWorkspace,
    sanitize_relative_path,
)
from thot.tools.ingest.worker import IngestWorker
from thot.tools.search.vespa_client import VespaClient

LOGGER = logging.getLogger(__name__)


class AppState:
    """Shared ingest runtime state."""

    def __init__(self) -> None:
        """Initialize store, worker, and optional Vespa client handles.

        Example:
            >>> from thot.tools.ingest.app import AppState
            >>> state = AppState()
            >>> state.store is not None
            True
        """
        settings = ingest_settings()
        self.settings = settings
        self.store = IngestStore(settings.root)
        self.worker = IngestWorker(self.store, settings=settings)
        self.vespa: VespaClient | None = None


def _ensure_app_state(app: FastAPI) -> AppState:
    """Return ingest AppState, initializing it if lifespan did not run.

    Uvicorn can skip lifespan when the ASGI stack reports it unsupported
    (seen after volume permission failures during early middleware init).
    Endpoints must not crash with ``AttributeError`` in that case.

    Example:
        >>> import inspect
        >>> inspect.isfunction(_ensure_app_state)
        True
    """
    state = getattr(app.state, "ingest", None)
    if isinstance(state, AppState):
        return state
    LOGGER.warning(
        "ingest AppState missing (lifespan skipped?); initializing on demand"
    )
    state = AppState()
    state.store.ensure_layout()
    if state.vespa is None:
        state.vespa = VespaClient()
    app.state.ingest = state
    return state


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize store layout and optional Vespa client.

    Example:
        >>> from thot.tools.ingest.app import lifespan
        >>> callable(lifespan)
        True
    """
    configure_json_logging(service=os.getenv("TKEIR_SERVICE", "tkeir-ingest"))
    # Always rebuild AppState so INGEST_ROOT / settings changes take effect
    # (TestClient runs lifespan per session; reusing a prior state points at
    # a deleted temp root and makes status lookups 404).
    state = AppState()
    state.store.ensure_layout()
    if state.vespa is None:
        state.vespa = VespaClient()
    app.state.ingest = state
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
    """Return the current action correlation id or allocate a new one.

    Example:
        >>> len(_correlation_id()) > 0
        True
    """
    return current_correlation_id() or new_action_id()


def _parse_json_object_field(
    raw: Any, *, field_name: str
) -> dict[str, Any] | None:
    """Parse an optional multipart JSON object field.

    Example:
        >>> _parse_json_object_field('{"a": 1}', field_name="metadata")
        {'a': 1}
    """
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
    """Reject path-only ``ontologies`` form fields (content must be uploaded).

    Example:
        >>> _parse_ontology_paths_field(None)  # no-op
    """
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
    """Persist multipart ontology file uploads and return staged absolute paths.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(_stage_uploaded_ontologies)
        True
    """
    from thot.tools.ingest.ontology_upload import stage_ontology_bytes

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
    """Build pipeline extras from multipart metadata + uploaded ontology bytes.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(_document_extras_from_multipart)
        True
    """
    from thot.tools.ingest.ontology_upload import strip_client_ontology_paths
    from thot.tools.ingest.worker import document_extras_from_metadata

    # Reject path-only ontology lists (client/server separation).
    _parse_ontology_paths_field(form.get("ontologies"))

    metadata = _parse_json_object_field(
        form.get("metadata"), field_name="metadata"
    )
    metadata = strip_client_ontology_paths(metadata)
    state = _ensure_app_state(app)
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
    index_target: str = "user",
) -> IngestAcceptedResponse:
    """Queue one ingest job and return the accepted response.

    Example:
        >>> import inspect
        >>> inspect.isfunction(_queue_job)
        True
    """
    state = _ensure_app_state(app)
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
        finished = await state.worker.process_source(
            ingest_id=ingest_id,
            correlation_id=correlation_id,
            source_uri=source_uri,
            content=content,
            filename=filename,
            content_type=content_type,
            batch_id=batch_id,
            user_space=user_space,
            document_extras=document_extras,
            index_target=index_target,
        )
        parsed = _parse_workspace_source_uri(source_uri)
        if parsed is None:
            return
        space, relative = parsed
        try:
            ws = UserWorkspace(space, root=state.settings.workspace_root)
            _apply_ingest_job_to_workspace(
                ws,
                state,
                relative,
                ingest_id=finished.ingest_id if finished else ingest_id,
            )
        except (
            Exception
        ):  # noqa: BLE001 — catalog sync must not fail the ingest task
            LOGGER.exception(
                "Failed to sync workspace catalog after ingest %s (%s)",
                ingest_id,
                source_uri,
            )

    background.add_task(_run)
    return IngestAcceptedResponse(
        ingest_id=ingest_id,
        correlation_id=correlation_id,
        status=IngestJobStatus.PENDING,
    )


def _job_status_value(job: Any) -> str:
    """Normalize an ingest job status to a string value.

    Example:
        >>> from thot.tools.ingest.models import IngestJob, IngestJobStatus
        >>> from thot.action.models import utc_now_rfc3339
        >>> now = utc_now_rfc3339()
        >>> job = IngestJob(
        ...     ingest_id="i1", correlation_id="c1",
        ...     status=IngestJobStatus.PENDING, created_at=now, updated_at=now,
        ... )
        >>> _job_status_value(job)
        'pending'
    """
    status = getattr(job, "status", None)
    if status is not None and hasattr(status, "value"):
        return str(status.value)
    return str(status or "")


def _parse_workspace_source_uri(source_uri: str) -> tuple[str, str] | None:
    """Parse ``workspace://{user_space}/{relative_path}`` → ``(space, path)``.

    Example:
        >>> _parse_workspace_source_uri("workspace://demo@tkeir/reports/a.md")
        ('demo@tkeir', 'reports/a.md')
    """
    prefix = "workspace://"
    if not source_uri.startswith(prefix):
        return None
    rest = source_uri[len(prefix) :]
    if "/" not in rest:
        return None
    space, relative = rest.split("/", 1)
    space = space.strip()
    relative = relative.strip()
    if not space or not relative:
        return None
    return space, relative


def _apply_ingest_job_to_workspace(
    ws: UserWorkspace,
    state: AppState,
    relative_path: str,
    *,
    ingest_id: str | None = None,
) -> dict[str, Any] | None:
    """Update a My-files catalog entry from its ingest job (success/noop/fail).

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.tools.ingest.store import IngestStore
        >>> from thot.tools.ingest.user_workspace import UserWorkspace, WorkspaceFileRecord
        >>> with tempfile.TemporaryDirectory() as temp_dir:
        ...     root = Path(temp_dir)
        ...     ws = UserWorkspace("demo@tkeir", root=root)
        ...     ws.ensure_layout()
        ...     _ = ws.upsert_record(WorkspaceFileRecord(
        ...         path="a.md", source_ref="s", status="indexing", ingest_id="missing",
        ...     ))
        ...     state = AppState()
        ...     state.store = IngestStore(root / "ingest")
        ...     state.store.ensure_layout()
        ...     applied = _apply_ingest_job_to_workspace(
        ...         ws, state, "a.md", ingest_id="missing",
        ...     )
        ...     applied["status"]
        'failed'
    """
    try:
        record = ws.get_record(relative_path)
    except ValueError:
        return None
    if record is None:
        return None
    job_id = ingest_id or record.ingest_id
    if not job_id:
        return record.to_dict()
    job = state.store.read_job(job_id)
    if job is None:
        # Job record gone (restart / cleanup) — do not keep the catalog stuck
        # on ``indexing`` or the HMI progress bar never reaches 100%.
        if record.status == "indexing":
            record.status = "failed"
            record.ingest_id = job_id
            ws.upsert_record(record)
            return record.to_dict()
        return record.to_dict()
    status = _job_status_value(job)
    if status in {"succeeded", "noop"}:
        analyzed = None
        if record.source_ref:
            analyzed = state.store.read_analyzed_document_by_source_ref(
                record.source_ref
            )
        if analyzed is None and job.doc_id:
            analyzed = state.store.read_analyzed_document(job.doc_id)
        synced = ws.sync_from_analyzed(
            relative_path, analyzed, status="indexed"
        )
        target = synced or record
        target.status = "indexed"
        if job.doc_id:
            target.doc_id = job.doc_id
        target.ingest_id = job_id
        if analyzed is None and not target.passage_ids:
            # Job finished (often noop) but analyzed payload missing — still
            # clear the stuck "indexing" badge so the HMI can progress.
            target.status = "indexed"
        ws.upsert_record(target)
        return target.to_dict()
    if status == "failed":
        record.status = "failed"
        record.ingest_id = job_id
        ws.upsert_record(record)
        return record.to_dict()
    if status in {"pending", "running"}:
        record.status = "indexing"
        record.ingest_id = job_id
        ws.upsert_record(record)
        return record.to_dict()
    return record.to_dict()


def _heal_workspace_indexing(ws: UserWorkspace, state: AppState) -> int:
    """Resolve catalog rows stuck on ``indexing`` after jobs finished.

    Example:
        >>> import inspect
        >>> inspect.isfunction(_heal_workspace_indexing)
        True
    """
    healed = 0
    for record in ws.iter_indexing_records():
        before = record.status
        applied = _apply_ingest_job_to_workspace(
            ws, state, record.path, ingest_id=record.ingest_id
        )
        if applied and applied.get("status") != before:
            healed += 1
    return healed


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — also ensures AppState exists (lifespan safeguard).

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import health
        >>> inspect.iscoroutinefunction(health)
        True
    """
    _ensure_app_state(app)
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    """Readiness probe: Vespa + embedding provider.

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import ready
        >>> inspect.iscoroutinefunction(ready)
        True
    """
    state = _ensure_app_state(app)
    vespa_ok = False
    if state.vespa is not None:
        vespa_ok = await state.vespa.health()
    report = await readiness_report(vespa_ok=vespa_ok)
    if report["status"] != "ready":
        raise HTTPException(status_code=503, detail=report)
    return report


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus exposition.

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import metrics
        >>> inspect.iscoroutinefunction(metrics)
        True
    """
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
    authorization: str | None = Header(default=None),
) -> IngestAcceptedResponse:
    """Ingest one document from multipart upload or JSON URL.

    Non-admin callers are limited to Vespa ``user`` streaming (personal index).
    Admins may select ``global`` / ``user`` / ``both``.

    Per-document external ontologies must be **uploaded as content** (the
    server has no access to client filesystem paths):

    - multipart: repeatable ``ontology_file`` parts (OWL/TTL/RDF bytes), and/or
    - JSON body: ``ontologies: [{filename, content_base64}, ...]``.

    Staged paths under ``INGEST_ROOT`` are passed to NER, syntax, and
    document-ontology for that document only.
    

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import ingest_document
        >>> inspect.iscoroutinefunction(ingest_document)
        True
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
        target_raw = form.get("index_target")
        target = resolve_allowed_index_target(
            str(target_raw) if isinstance(target_raw, str) else None,
            authorization=authorization,
            default="user",
            admin_default="global",
        )
        source_doc_id = form.get("source_doc_id")
        if isinstance(source_doc_id, str) and source_doc_id.strip():
            if extras is None:
                extras = {}
            extras["source_doc_id"] = source_doc_id.strip()
        return _queue_job(
            source_uri=source_uri,
            content=content,
            filename=filename,
            content_type=getattr(upload_obj, "content_type", None),
            batch_id=None,
            background=background,
            user_space=actor,
            document_extras=extras,
            index_target=target,
        )
    try:
        body = DocumentIngestRequest.model_validate(await request.json())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    from thot.tools.ingest.ontology_upload import (
        decode_ontology_uploads,
        stage_ontology_bytes,
        strip_client_ontology_paths,
    )
    from thot.tools.ingest.worker import document_extras_from_metadata

    state = _ensure_app_state(app)
    staging_id = new_action_id()
    try:
        uploads = decode_ontology_uploads(
            [item.model_dump() for item in body.ontologies or []]
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
    target = resolve_allowed_index_target(
        None,
        authorization=authorization,
        default="user",
        admin_default="global",
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
        index_target=target,
    )


@app.post(
    "/ingest/json-records",
    response_model=JsonRecordsAcceptedResponse,
    status_code=202,
)
async def ingest_json_records(
    request: Request,
    background: BackgroundTasks,
    actor: str = Depends(require_admin_ingest),
    authorization: str | None = Header(default=None),
) -> JsonRecordsAcceptedResponse:
    """Split a record-oriented JSON corpus into markdown docs and queue NLP+index.

    **Admin-only** global corpus path (shared Vespa ``global`` schema by default).
    Non-admin users must use My files / ``/workspace/*`` (personal ``user`` index).

    Each record becomes one document:
    - source / source_doc_id = ``{filename_stem}/{doc_id}``
    - body = Markdown of title, text, and every attribute
    - structured fields (not title/text) → ``record_concept_ids`` (Vespa ontology)

    Accepts multipart ``file`` upload **or** JSON body with ``dataset_path``
    (resolved under the repo ``datasets/`` tree for admin demos).
    

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import ingest_json_records
        >>> inspect.iscoroutinefunction(ingest_json_records)
        True
    """
    from thot.core.TkeirPaths import repo_root
    from thot.tools.ingest.json_records import (
        corpus_filename_stem,
        load_and_split,
    )
    from thot.tools.ingest.worker import document_extras_from_metadata

    content_type = request.headers.get("content-type", "")
    options = JsonRecordsIngestRequest()
    content: bytes | None = None
    filename = "corpus.json"

    if content_type.startswith("multipart/"):
        form = await request.form()
        raw_opts = form.get("options")
        if raw_opts is not None and not hasattr(raw_opts, "read"):
            try:
                options = JsonRecordsIngestRequest.model_validate(
                    json.loads(str(raw_opts))
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=400, detail=f"Invalid options JSON: {exc}"
                ) from exc
        upload = form.get("file")
        if upload is not None and hasattr(upload, "read"):
            upload_obj = cast(Any, upload)
            content = await upload_obj.read()
            filename = getattr(upload_obj, "filename", None) or filename
        elif options.dataset_path:
            pass
        else:
            raise HTTPException(
                status_code=400,
                detail="Provide multipart file or options.dataset_path",
            )
    else:
        try:
            options = JsonRecordsIngestRequest.model_validate(
                await request.json()
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if options.filename:
            filename = options.filename

    if content is None:
        if not options.dataset_path:
            raise HTTPException(
                status_code=400,
                detail="dataset_path required when no file is uploaded",
            )
        root = Path(repo_root()).resolve()
        datasets_root = (root / "datasets").resolve()
        candidate = Path(options.dataset_path)
        if not candidate.is_absolute():
            candidate = (datasets_root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        try:
            candidate.relative_to(datasets_root)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="dataset_path must stay under datasets/",
            ) from exc
        if not candidate.is_file():
            raise HTTPException(
                status_code=404, detail=f"Dataset not found: {candidate.name}"
            )
        content = candidate.read_bytes()
        filename = options.filename or candidate.name

    target = resolve_allowed_index_target(
        options.index_target,
        authorization=authorization,
        default="global",
        admin_default="global",
        require_admin_for_global=True,
    )
    if not options.split_records:
        raise HTTPException(
            status_code=400,
            detail="split_records=false is not supported yet; upload as .md",
        )

    try:
        documents = load_and_split(
            content,
            filename=filename,
            offset=options.offset,
            limit=options.limit,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    batch_id = new_action_id()
    correlation_id = _correlation_id()
    jobs: list[IngestAcceptedResponse] = []
    for doc in documents:
        meta = dict(doc.get("metadata") or {})
        extras = document_extras_from_metadata(meta) or {}
        extras["source_doc_id"] = doc["source_doc_id"]
        extras["source"] = doc["source"]
        extras["record_concept_ids"] = list(
            doc.get("record_concept_ids") or []
        )
        extras["index_target"] = target
        extras["title"] = doc.get("title")
        md_bytes = str(doc["markdown"]).encode("utf-8")
        accepted = _queue_job(
            source_uri=f"json-record://{batch_id}/{doc['doc_id']}",
            content=md_bytes,
            filename=str(doc["filename"]),
            content_type="text/markdown",
            batch_id=batch_id,
            background=background,
            user_space=actor,
            document_extras=extras,
            index_target=target,
        )
        jobs.append(accepted)

    return JsonRecordsAcceptedResponse(
        batch_id=batch_id,
        correlation_id=correlation_id,
        record_count=len(documents),
        queued=len(jobs),
        index_target=target,
        source_basename=corpus_filename_stem(filename),
        jobs=jobs,
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
    authorization: str | None = Header(default=None),
) -> BatchAcceptedResponse:
    """Queue a batch of URL-based ingest jobs (each item may carry ontologies).

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import ingest_batch
        >>> inspect.iscoroutinefunction(ingest_batch)
        True
    """
    from thot.tools.ingest.ontology_upload import (
        decode_ontology_uploads,
        stage_ontology_bytes,
        strip_client_ontology_paths,
    )
    from thot.tools.ingest.worker import document_extras_from_metadata

    state = _ensure_app_state(app)
    batch_id = new_action_id()
    correlation_id = _correlation_id()
    target = resolve_allowed_index_target(
        None,
        authorization=authorization,
        default="user",
        admin_default="global",
    )
    jobs: list[IngestAcceptedResponse] = []
    for item in request.items:
        staging_id = new_action_id()
        try:
            uploads = decode_ontology_uploads(
                [o.model_dump() for o in item.ontologies or []]
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
            index_target=target,
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
    include_manifest: bool = False,
    _actor: str = Depends(require_ingest_auth),
) -> IngestStatusResponse:
    """Return job status (and optionally the full staging manifest).

    HMI progress polling must stay lightweight: loading every manifest on each
    tick overloaded the server and left transient ``poll_error`` statuses that
    never counted as done, so the progress bar stalled below 100%.
    

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import ingest_status
        >>> inspect.iscoroutinefunction(ingest_status)
        True
    """
    state = _ensure_app_state(app)
    job = state.store.read_job(ingest_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown ingest id")
    manifest = None
    if include_manifest and job.doc_id:
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
    """Stop the ingest server process (used by client ``--stop-on-failed``).

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import ingest_stop
        >>> inspect.iscoroutinefunction(ingest_stop)
        True
    """
    import threading

    from thot.tools.ingest.shutdown import request_ingest_shutdown

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


def _user_workspace_for(actor: str) -> UserWorkspace:
    """Return a layout-initialized workspace for ``actor``.

    Example:
        >>> import inspect
        >>> inspect.isfunction(_user_workspace_for)
        True
    """
    state = _ensure_app_state(app)
    ws = UserWorkspace(actor, root=state.settings.workspace_root)
    ws.ensure_layout()
    return ws


# Cross-user share allowlist (analyst / humint / watch → commander received/).
_WORKSPACE_SHARE_TARGETS = frozenset({"commander"})
# Top-level My-files folder where shared documents land for the recipient.
_WORKSPACE_RECEIVED_PREFIX = "received"


@app.get("/workspace/tree")
async def workspace_tree(
    path: str = "",
    actor: str = Depends(require_ingest_auth),
) -> dict[str, Any]:
    """List the authenticated user's workspace directory.

    Also heals catalog rows stuck on ``indexing`` when their ingest jobs
    have already finished (success / noop / failed).
    

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import workspace_tree
        >>> inspect.iscoroutinefunction(workspace_tree)
        True
    """
    ws = _user_workspace_for(actor)
    state = _ensure_app_state(app)
    try:
        _heal_workspace_indexing(ws, state)
        return ws.list_dir(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/workspace/mkdir")
async def workspace_mkdir(
    request: Request,
    actor: str = Depends(require_ingest_auth),
) -> dict[str, Any]:
    """Create a directory under the user's workspace ``files/`` tree.

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import workspace_mkdir
        >>> inspect.iscoroutinefunction(workspace_mkdir)
        True
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    relative = str((body or {}).get("path") or "").strip()
    try:
        created = _user_workspace_for(actor).mkdir(relative)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": created, "kind": "directory"}


@app.post("/workspace/upload", status_code=202)
async def workspace_upload(
    request: Request,
    background: BackgroundTasks,
    actor: str = Depends(require_ingest_auth),
) -> dict[str, Any]:
    """Save a file into the user workspace (default: store only, no index).

    Multipart fields:
    - ``file`` (required)
    - ``path`` optional relative path (defaults to filename under current folder)
    - ``directory`` optional parent directory for the filename
    - ``index`` optional ``true``/``false`` (default **false** — Index selected)

    When the upload is a record-oriented JSON corpus (``{records:[…]}``),
    each record is converted to Markdown and saved as
    ``{directory}/{corpus_stem}/{doc_id}.md`` (personal workspace only).
    

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import workspace_upload
        >>> inspect.iscoroutinefunction(workspace_upload)
        True
    """
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("multipart/"):
        raise HTTPException(
            status_code=400, detail="multipart/form-data required"
        )
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        raise HTTPException(status_code=400, detail="Missing file field")
    upload_obj = cast(Any, upload)
    content = await upload_obj.read()
    filename = getattr(upload_obj, "filename", None) or "upload.bin"
    path_field = form.get("path")
    directory = form.get("directory")
    index_raw = form.get("index")
    # My files: store only by default; user must Index selected explicitly.
    do_index = False
    if isinstance(index_raw, str) and index_raw.strip():
        do_index = index_raw.strip().lower() in {"1", "true", "yes", "on"}

    parent = (
        str(directory).strip().strip("/")
        if isinstance(directory, str) and directory.strip()
        else ""
    )
    if isinstance(path_field, str) and path_field.strip():
        relative = path_field.strip()
        # If path is a file under a folder, use that folder as parent for splits.
        if "/" in relative and relative.lower().endswith(".json"):
            parent = "/".join(relative.split("/")[:-1])
    else:
        relative = f"{parent}/{filename}".lstrip("/") if parent else filename

    ws = _user_workspace_for(actor)

    # Record JSON corpora → one markdown file per doc_id.
    if filename.lower().endswith(".json") or (
        isinstance(relative, str) and relative.lower().endswith(".json")
    ):
        from thot.tools.ingest.json_records import (
            workspace_markdown_files_from_json,
        )

        split_docs = workspace_markdown_files_from_json(
            content,
            filename=filename,
            directory=parent,
        )
        if split_docs is not None:
            created: list[dict[str, Any]] = []
            queued: list[dict[str, Any]] = []
            for doc in split_docs:
                md_bytes = str(doc["markdown"]).encode("utf-8")
                try:
                    record = ws.write_file(
                        str(doc["path"]),
                        md_bytes,
                        content_type="text/markdown",
                        status="pending",
                    )
                except ValueError as exc:
                    raise HTTPException(
                        status_code=400, detail=str(exc)
                    ) from exc
                entry: dict[str, Any] = {
                    "path": record.path,
                    "doc_id": doc.get("doc_id"),
                    "source_ref": record.source_ref,
                    "status": record.status,
                }
                if do_index:
                    extras = {
                        "source_doc_id": record.source_ref,
                        "title": doc.get("title") or Path(record.path).stem,
                        "language": "en",
                        "index_target": "user",
                        "dataset": _default_business_ontology_dataset(),
                        "business_ontology_dataset": (
                            _default_business_ontology_dataset()
                        ),
                        "force_reindex": True,
                    }
                    concepts = doc.get("record_concept_ids") or []
                    if concepts:
                        extras["record_concept_ids"] = concepts
                    accepted = _queue_job(
                        source_uri=f"workspace://{actor}/{record.path}",
                        content=md_bytes,
                        filename=Path(record.path).name,
                        content_type="text/markdown",
                        batch_id=None,
                        background=background,
                        user_space=actor,
                        document_extras=extras,
                        index_target="user",
                    )
                    record.ingest_id = accepted.ingest_id
                    record.status = "indexing"
                    ws.upsert_record(record)
                    entry["ingest_id"] = accepted.ingest_id
                    entry["status"] = "indexing"
                    queued.append(entry)
                created.append(entry)
            folder = (
                str(Path(created[0]["path"]).parent) if created else parent
            )
            return {
                "split_records": True,
                "folder": folder,
                "user_space": actor,
                "created_count": len(created),
                "queued_count": len(queued),
                "created": created[:50],
                "created_paths": [item["path"] for item in created],
                "index_target": "user" if do_index else None,
            }

    try:
        record = ws.write_file(
            relative,
            content,
            content_type=getattr(upload_obj, "content_type", None),
            status="pending",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not do_index:
        return {
            "path": record.path,
            "source_ref": record.source_ref,
            "user_space": actor,
            "ingest_id": None,
            "status": "pending",
            "index_target": None,
            "split_records": False,
        }

    extras = {
        "source_doc_id": record.source_ref,
        "title": Path(filename).stem,
        "language": "en",
        "index_target": "user",
        "dataset": _default_business_ontology_dataset(),
        "business_ontology_dataset": _default_business_ontology_dataset(),
        "force_reindex": True,
    }
    accepted = _queue_job(
        source_uri=f"workspace://{actor}/{record.path}",
        content=content,
        filename=filename,
        content_type=getattr(upload_obj, "content_type", None),
        batch_id=None,
        background=background,
        user_space=actor,
        document_extras=extras,
        index_target="user",
    )
    record.ingest_id = accepted.ingest_id
    record.status = "indexing"
    ws.upsert_record(record)
    return {
        "path": record.path,
        "source_ref": record.source_ref,
        "user_space": actor,
        "ingest_id": accepted.ingest_id,
        "correlation_id": accepted.correlation_id,
        "status": accepted.status,
        "index_target": "user",
        "split_records": False,
    }


@app.get("/workspace/file")
async def workspace_read_file(
    path: str,
    actor: str = Depends(require_ingest_auth),
) -> dict[str, Any]:
    """Read a workspace file for HMI preview (text / markdown).

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import workspace_read_file
        >>> inspect.iscoroutinefunction(workspace_read_file)
        True
    """
    ws = _user_workspace_for(actor)
    try:
        file_path = ws.resolve_file(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    # Cap preview size (2 MiB) to keep HMI responsive.
    max_bytes = 2 * 1024 * 1024
    size = file_path.stat().st_size
    if size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"file too large to preview ({size} bytes; max {max_bytes})",
        )
    raw = file_path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=415,
            detail="file is not UTF-8 text",
        ) from None
    record = None
    try:
        record = ws.get_record(path)
    except ValueError:
        record = None
    return {
        "path": path,
        "name": file_path.name,
        "size_bytes": size,
        "content_type": (
            (record.content_type if record else None)
            or (
                "text/markdown"
                if path.lower().endswith((".md", ".markdown"))
                else "text/plain"
            )
        ),
        "content": text,
        "status": record.status if record else "untracked",
        "source_ref": record.source_ref if record else None,
    }


@app.post("/workspace/copy-to")
async def workspace_copy_to(
    request: Request,
    actor: str = Depends(require_ingest_auth),
) -> dict[str, Any]:
    """Copy selected files into another user's My files (no index).

    Body::
        {
          "paths": ["reports/a.md", ...],
          "target_user_space": "commander",
          "dest_prefix": "received"   # optional; default received/<source>
        }

    Files land under the recipient's dedicated ``received/`` folder (flattened
    to the basename so they are visible without deep navigation). Only
    allowlisted targets (``commander``) are accepted. Destination catalog
    entries are ``pending`` so the recipient can choose what to index.
    

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import workspace_copy_to
        >>> inspect.iscoroutinefunction(workspace_copy_to)
        True
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    paths_raw = (body or {}).get("paths") or []
    if not isinstance(paths_raw, list) or not paths_raw:
        raise HTTPException(
            status_code=400, detail="paths must be a non-empty list"
        )
    target_raw = str((body or {}).get("target_user_space") or "").strip()
    if not target_raw:
        raise HTTPException(
            status_code=400, detail="target_user_space is required"
        )
    dest_prefix_raw = str((body or {}).get("dest_prefix") or "").strip()

    source = _user_workspace_for(actor)
    target = UserWorkspace(
        target_raw, root=_ensure_app_state(app).settings.workspace_root
    )
    target.ensure_layout()
    if target.user_space not in _WORKSPACE_SHARE_TARGETS:
        raise HTTPException(
            status_code=403,
            detail=(
                f"target_user_space {target.user_space!r} is not allowed; "
                f"allowed={sorted(_WORKSPACE_SHARE_TARGETS)}"
            ),
        )
    if target.user_space == source.user_space:
        raise HTTPException(
            status_code=400, detail="cannot copy into your own workspace"
        )

    if dest_prefix_raw:
        try:
            dest_prefix = sanitize_relative_path(
                dest_prefix_raw, allow_empty=False
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        dest_prefix = f"{_WORKSPACE_RECEIVED_PREFIX}/{source.user_space}"

    # Ensure the dedicated received folder (and per-sender subfolder) exist.
    try:
        target.mkdir(dest_prefix)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    copied: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for raw_path in paths_raw:
        rel = str(raw_path or "").strip()
        if not rel:
            continue
        try:
            src_rel = sanitize_relative_path(rel, allow_empty=False)
            content = source.read_file_bytes(src_rel)
            src_record = source.get_record(src_rel)
            dest_rel = _received_dest_path(target, dest_prefix, src_rel)
            dest_record = target.write_file(
                dest_rel,
                content,
                content_type=src_record.content_type if src_record else None,
                status="pending",
                copied_from_user=source.user_space,
                copied_from_path=src_rel,
                copied_from_source_ref=(
                    src_record.source_ref
                    if src_record
                    else source.source_ref_for(src_rel)
                ),
            )
            copied.append(
                {
                    "from": src_rel,
                    "to": dest_record.path,
                    "source_ref": dest_record.source_ref,
                    "status": dest_record.status,
                }
            )
        except (ValueError, FileNotFoundError, OSError) as exc:
            errors.append({"path": rel, "error": str(exc)})

    return {
        "source_user_space": source.user_space,
        "target_user_space": target.user_space,
        "dest_prefix": dest_prefix,
        "copied": copied,
        "errors": errors,
        "copied_count": len(copied),
    }


def _received_dest_path(
    target: UserWorkspace, dest_prefix: str, src_rel: str
) -> str:
    """Place ``src_rel`` under ``dest_prefix`` using a unique basename.

    Keeps the recipient's ``received/`` folder shallow and browsable.

    Example:
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as temp_dir:
        ...     target = UserWorkspace("cmd@tkeir", root=temp_dir)
        ...     target.ensure_layout()
        ...     _received_dest_path(target, "received/analyst", "inbox/x/report.md")
        'received/analyst/report.md'
    """
    from pathlib import Path as _Path

    base_name = _Path(src_rel).name or "document.md"
    candidate = f"{dest_prefix}/{base_name}"
    if not _received_path_taken(target, candidate):
        return candidate
    stem = _Path(base_name).stem
    suffix = _Path(base_name).suffix
    # Prefer a stable disambiguator from the source relative path.
    parent = _Path(src_rel).parent.as_posix().replace("/", "_").strip("._")
    if parent and parent != ".":
        candidate = f"{dest_prefix}/{parent}_{base_name}"
        if not _received_path_taken(target, candidate):
            return candidate
    for index in range(2, 1000):
        candidate = f"{dest_prefix}/{stem}_{index}{suffix}"
        if not _received_path_taken(target, candidate):
            return candidate
    raise ValueError(f"could not allocate unique path under {dest_prefix!r}")


def _received_path_taken(target: UserWorkspace, relative_path: str) -> bool:
    """Return True when ``relative_path`` exists in catalog or on disk.

    Example:
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as temp_dir:
        ...     target = UserWorkspace("cmd@tkeir", root=temp_dir)
        ...     target.ensure_layout()
        ...     _received_path_taken(target, "missing.md")
        False
    """
    if target.get_record(relative_path) is not None:
        return True
    try:
        return target.resolve_file(relative_path).exists()
    except ValueError:
        return False


def _default_business_ontology_dataset() -> str:
    """Return rag.yaml ``dual_hybrid.business_ontology.default_dataset`` (osint).

    Example:
        >>> isinstance(_default_business_ontology_dataset(), str)
        True
    """
    try:
        from thot.tools.search.rag_config import load_rag_config

        name = (
            load_rag_config().dual_hybrid.business_ontology.default_dataset
            or ""
        ).strip()
        if name:
            return name
    except Exception:  # noqa: BLE001 — ingest must not fail without rag.yaml
        LOGGER.debug(
            "Could not load rag.yaml business ontology default", exc_info=True
        )
    return "osint"


@app.post("/workspace/index", status_code=202)
async def workspace_index(
    request: Request,
    background: BackgroundTasks,
    actor: str = Depends(require_ingest_auth),
) -> dict[str, Any]:
    """Queue Vespa user-index jobs for existing workspace files (no rewrite).

    Body::
        {
          "paths": ["inbox/analyst/report.md", ...],
          "business_ontology_dataset": "osint",   # optional
          "business_ontology": { "concepts": [...] }  # optional inline override
        }

    Loads ``datasets/<business_ontology_dataset>/business_ontology.yaml``,
    runs the NLP pipeline, annotates the analyzed document with matched
    concepts, then indexes into the personal ``user`` streaming group.
    

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import workspace_index
        >>> inspect.iscoroutinefunction(workspace_index)
        True
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    paths_raw = (body or {}).get("paths") or []
    if not isinstance(paths_raw, list) or not paths_raw:
        raise HTTPException(
            status_code=400, detail="paths must be a non-empty list"
        )

    bo_dataset = (
        str((body or {}).get("business_ontology_dataset") or "").strip()
        or _default_business_ontology_dataset()
    )
    bo_payload = (body or {}).get("business_ontology")

    ws = _user_workspace_for(actor)
    queued: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for raw_path in paths_raw:
        rel = str(raw_path or "").strip()
        if not rel:
            continue
        try:
            src_rel = sanitize_relative_path(rel, allow_empty=False)
            content = ws.read_file_bytes(src_rel)
            record = ws.get_record(src_rel)
            if record is None:
                record = ws.write_file(
                    src_rel,
                    content,
                    status="pending",
                )
            filename = Path(src_rel).name
            extras: dict[str, Any] = {
                "source_doc_id": record.source_ref,
                "title": Path(filename).stem,
                "language": "en",
                "index_target": "user",
                "dataset": bo_dataset,
                "business_ontology_dataset": bo_dataset,
                # Explicit Index selected must re-run NLP + BO annotation.
                "force_reindex": True,
            }
            if bo_payload is not None:
                extras["business_ontology"] = bo_payload
            accepted = _queue_job(
                source_uri=f"workspace://{actor}/{record.path}",
                content=content,
                filename=filename,
                content_type=record.content_type,
                batch_id=None,
                background=background,
                user_space=actor,
                document_extras=extras,
                index_target="user",
            )
            record.ingest_id = accepted.ingest_id
            record.status = "indexing"
            ws.upsert_record(record)
            queued.append(
                {
                    "path": record.path,
                    "source_ref": record.source_ref,
                    "ingest_id": accepted.ingest_id,
                    "status": accepted.status,
                }
            )
        except (ValueError, FileNotFoundError, OSError) as exc:
            errors.append({"path": rel, "error": str(exc)})

    return {
        "user_space": actor,
        "queued": queued,
        "errors": errors,
        "queued_count": len(queued),
        "index_target": "user",
        "business_ontology_dataset": bo_dataset,
    }


@app.post("/workspace/sync")
async def workspace_sync(
    request: Request,
    actor: str = Depends(require_ingest_auth),
) -> dict[str, Any]:
    """Refresh catalog passage ids from ingest analyzed documents / job status.

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import workspace_sync
        >>> inspect.iscoroutinefunction(workspace_sync)
        True
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    relative = str((body or {}).get("path") or "").strip()
    if not relative:
        raise HTTPException(status_code=400, detail="path is required")
    ws = _user_workspace_for(actor)
    record = ws.get_record(relative)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown workspace file")
    state = _ensure_app_state(app)
    applied = _apply_ingest_job_to_workspace(
        ws, state, relative, ingest_id=record.ingest_id
    )
    return applied or {"path": relative}


@app.post("/workspace/status")
async def workspace_status(
    request: Request,
    actor: str = Depends(require_ingest_auth),
) -> dict[str, Any]:
    """Return (and heal) indexing status for selected My-files paths.

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import workspace_status
        >>> inspect.iscoroutinefunction(workspace_status)
        True
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    paths_raw = (body or {}).get("paths") or []
    if not isinstance(paths_raw, list):
        raise HTTPException(status_code=400, detail="paths must be a list")
    ws = _user_workspace_for(actor)
    state = _ensure_app_state(app)
    _heal_workspace_indexing(ws, state)
    files: list[dict[str, Any]] = []
    counts = {"indexing": 0, "indexed": 0, "failed": 0, "other": 0}
    for raw in paths_raw:
        rel = str(raw or "").strip()
        if not rel:
            continue
        try:
            record = ws.get_record(rel)
        except ValueError:
            files.append({"path": rel, "status": "invalid"})
            counts["other"] += 1
            continue
        if record is None:
            files.append({"path": rel, "status": "missing"})
            counts["other"] += 1
            continue
        status = (record.status or "other").lower()
        if status in counts:
            counts[status] += 1
        else:
            counts["other"] += 1
        files.append(
            {
                "path": record.path,
                "status": record.status,
                "passage_count": len(record.passage_ids or []),
                "ingest_id": record.ingest_id,
            }
        )
    return {
        "user_space": actor,
        "files": files,
        "counts": counts,
        "total": len(files),
        "done": counts["indexed"] + counts["failed"],
        "active": counts["indexing"] > 0,
    }


@app.delete("/workspace/file")
async def workspace_delete_file(
    path: str,
    actor: str = Depends(require_ingest_auth),
) -> dict[str, Any]:
    """Delete a workspace file and remove its passages from the user streaming index.

    Example:
        >>> import inspect
        >>> from thot.tools.ingest.app import workspace_delete_file
        >>> inspect.iscoroutinefunction(workspace_delete_file)
        True
    """
    ws = _user_workspace_for(actor)
    try:
        record = ws.get_record(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        # Still allow deleting an untracked file/dir from the tree.
        try:
            removed = ws.delete_file(path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "path": path,
            "deleted_from_workspace": removed is not None or True,
            "unindex": None,
        }

    state = _ensure_app_state(app)
    # Prefer catalog passage ids; refresh from analyzed doc when empty.
    if not record.passage_ids:
        analyzed = state.store.read_analyzed_document_by_source_ref(
            record.source_ref
        )
        synced = ws.sync_from_analyzed(path, analyzed)
        if synced:
            record = synced

    unindex: dict[str, Any] | None = None
    if state.vespa is not None:
        try:
            unindex = await state.vespa.delete_user_passages_by_source_ref(
                record.source_ref,
                user_space=actor,
                passage_ids=record.passage_ids or None,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Failed to unindex workspace file %s", path)
            raise HTTPException(
                status_code=502,
                detail=f"Vespa unindex failed: {exc}",
            ) from exc

    try:
        ws.delete_file(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "path": path,
        "source_ref": record.source_ref,
        "deleted_from_workspace": True,
        "unindex": unindex,
    }


def main() -> None:
    """CLI entry point for the ingest FastAPI server or maintenance CLI.

    Example:
        >>> from thot.tools.ingest.app import main
        >>> callable(main)
        True
    """
    import sys

    import uvicorn

    if len(sys.argv) > 1 and sys.argv[1] == "retry":
        from thot.tools.ingest.cli import main as cli_main

        cli_main()
        return

    settings = ingest_settings()
    from thot.core.StructuredLogging import configure_text_logging

    configure_text_logging(level=logging.INFO, force=True)
    uvicorn.run(
        "thot.tools.ingest.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
