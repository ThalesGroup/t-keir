"""Title: tkeir-okf FastAPI service (:8095).

HTTP service for OKF bundle export / browse / download / DSR delete.
Core OKF library remains in ``thot.okf``.

Example:
    >>> from thot.tools.okf.app import app
    >>> app.title
    'T-KEIR OKF'

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

import httpx
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
from thot.okf.models import (
    OkfExportRequest,
    OkfExportResult,
    OkfHttpExportBody,
    OkfPublishWikiBody,
    OkfWikiUpdateBody,
)
from thot.okf.store import OkfBundleStore
from thot.okf.wiki import suggested_workspace_wiki_path, write_llm_wiki
from thot.tools.search.user_space import resolve_vespa_user_space

LOGGER = logging.getLogger(__name__)


class AppState:
    """Per-process OKF service state attached to ``FastAPI.state.okf``."""

    def __init__(self) -> None:
        """Initialize store and shared resources for the OKF HTTP service.

        Example:
            >>> from thot.tools.okf.app import AppState
            >>> isinstance(AppState().store, OkfBundleStore)
            True
        """
        self.store = OkfBundleStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Configure logging, metrics, and ``AppState`` at startup.

    Args:
        app: FastAPI application instance.

    Example:
        >>> import inspect
        >>> from thot.tools.okf.app import lifespan
        >>> inspect.isasyncgenfunction(lifespan.__wrapped__)
        True
    """
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
    """Resolve tenant user-space from the ``Authorization`` header.

    Args:
        authorization: Bearer token or ``None`` for dev default.

    Returns:
        Normalized Vespa user-space string.

    Example:
        >>> from thot.tools.okf.app import _space
        >>> _space(None)
        'dev@tkeir'
    """
    return resolve_vespa_user_space(authorization)


def _store(request_app: FastAPI) -> OkfBundleStore:
    """Return the bundle store from application state.

    Args:
        request_app: FastAPI app with ``state.okf`` initialized.

    Example:
        >>> from thot.tools.okf.app import AppState, _store, app
        >>> app.state.okf = AppState()
        >>> _store(app) is app.state.okf.store
        True
    """
    return request_app.state.okf.store


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe.

    Example:
        >>> import inspect
        >>> from thot.tools.okf.app import health
        >>> inspect.iscoroutinefunction(health)
        True
    """
    return {"status": "ok", "service": "tkeir-okf"}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    """Readiness probe with OKF root path and writability.

    Example:
        >>> import inspect
        >>> from thot.tools.okf.app import ready
        >>> inspect.iscoroutinefunction(ready)
        True
    """
    root = _store(app).root
    return {
        "status": "ready",
        "okf_root": str(root),
        "writable": os.access(root, os.W_OK),
    }


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics exposition endpoint.

    Example:
        >>> import inspect
        >>> from thot.tools.okf.app import metrics
        >>> inspect.iscoroutinefunction(metrics)
        True
    """
    return Response(
        content=ThotMetrics.generateMetricsResponse(),
        media_type="text/plain; version=0.0.4",
    )


@app.post("/okf/export", response_model=OkfExportResult)
async def okf_export(
    body: OkfHttpExportBody,
    authorization: str | None = Header(default=None),
) -> OkfExportResult:
    """Start an OKF export. ``user_space`` always comes from auth.

    Example:
        >>> import inspect
        >>> from thot.tools.okf.app import okf_export
        >>> inspect.iscoroutinefunction(okf_export)
        True
    """
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
    """List OKF bundles for the authenticated tenant.

    Example:
        >>> import inspect
        >>> from thot.tools.okf.app import okf_bundles
        >>> inspect.iscoroutinefunction(okf_bundles)
        True
    """
    space = _space(authorization)
    bundles = _store(app).list_bundles(space)
    return {
        "user_space": space,
        "bundles": [b.model_dump(mode="json") for b in bundles],
    }


def _bundle_missing(space: str, bundle_id: str) -> HTTPException:
    """Build a 404 when a bundle is not found for the tenant.

    Args:
        space: Tenant user-space.
        bundle_id: Requested bundle id.

    Example:
        >>> from thot.tools.okf.app import _bundle_missing
        >>> _bundle_missing("dev@tkeir", "abc12345").status_code
        404
    """
    return HTTPException(
        status_code=404,
        detail=(
            f"bundle not found for user_space={space} (id={bundle_id[:8]}…)"
        ),
    )


@app.get("/okf/bundles/{bundle_id}")
async def okf_bundle_get(
    bundle_id: str,
    concept_id: str | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return bundle payload or a single concept for the authenticated tenant.

    Example:
        >>> import inspect
        >>> from thot.tools.okf.app import okf_bundle_get
        >>> inspect.iscoroutinefunction(okf_bundle_get)
        True
    """
    space = _space(authorization)
    payload = _store(app).bundle_payload(
        bundle_id, space, concept_id=concept_id
    )
    if payload is None:
        raise _bundle_missing(space, bundle_id)
    return payload


@app.get("/okf/bundles/{bundle_id}/download")
async def okf_bundle_download(
    bundle_id: str,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> FileResponse:
    """Download a bundle as ``.tar.gz`` for the authenticated tenant.

    Example:
        >>> import inspect
        >>> from thot.tools.okf.app import okf_bundle_download
        >>> inspect.iscoroutinefunction(okf_bundle_download)
        True
    """
    space = _space(authorization)
    bundle = _store(app).get_bundle(bundle_id, space)
    if bundle is None:
        raise _bundle_missing(space, bundle_id)
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


@app.get("/okf/bundles/{bundle_id}/wiki-extract")
async def okf_wiki_extract(
    bundle_id: str,
    max_chars: int = 2400,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return Answer (+ Structured facts) extract from ``wiki.md`` for RAG/agents.

    No LLM — storage helper only. ``user_space`` comes from auth.

    Example:
        >>> import inspect
        >>> from thot.tools.okf.app import okf_wiki_extract
        >>> inspect.iscoroutinefunction(okf_wiki_extract)
        True
    """
    from thot.okf.wiki_match import wiki_extract_for_bundle

    space = _space(authorization)
    payload = wiki_extract_for_bundle(
        bundle_id,
        space,
        store=_store(app),
        max_chars=max(200, min(int(max_chars or 2400), 12000)),
    )
    if not payload.get("found"):
        raise _bundle_missing(space, bundle_id)
    return payload


@app.get("/okf/wikis/match")
async def okf_wiki_match(
    q: str,
    threshold: float = 0.15,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Find the closest user wiki by scoring ``index.md`` against ``q``.

    Example:
        >>> import inspect
        >>> from thot.tools.okf.app import okf_wiki_match
        >>> inspect.iscoroutinefunction(okf_wiki_match)
        True
    """
    from thot.okf.wiki_match import find_closest_wiki

    space = _space(authorization)
    query = (q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="q is required")
    match = find_closest_wiki(
        space,
        query,
        store=_store(app),
        threshold=float(threshold),
    )
    if match is None:
        return {
            "found": False,
            "user_space": space,
            "query": query,
            "threshold": float(threshold),
            "match": None,
        }
    return {
        "found": True,
        "user_space": space,
        "query": query,
        "threshold": float(threshold),
        "match": {
            "bundle_id": match.bundle_id,
            "score": match.score,
            "title": match.title,
            "path": match.path,
            "query": match.query,
        },
    }


@app.put("/okf/bundles/{bundle_id}/wiki")
async def okf_wiki_put(
    bundle_id: str,
    body: OkfWikiUpdateBody,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Save an edited LLMWiki page into the bundle (``wiki.md``).

    Example:
        >>> import inspect
        >>> from thot.tools.okf.app import okf_wiki_put
        >>> inspect.iscoroutinefunction(okf_wiki_put)
        True
    """
    ThotMetrics.increment_counter(
        short_name="okf_http",
        method="PUT",
        path="/okf/bundles/{bundle_id}/wiki",
        status=200,
    )
    space = _space(authorization)
    store = _store(app)
    try:
        path = store.put_wiki(bundle_id, space, body.markdown)
    except FileNotFoundError as exc:
        raise _bundle_missing(space, bundle_id) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "bundle_id": bundle_id,
        "wiki_path": "wiki.md",
        "path": path,
        "bytes": len(body.markdown.encode("utf-8")),
        "user_space": space,
    }


@app.post("/okf/bundles/{bundle_id}/publish-wiki")
async def okf_publish_wiki(
    bundle_id: str,
    body: OkfPublishWikiBody | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Copy the bundle LLMWiki page into the user's personal workspace and index it.

    Requires ingest at ``INGEST_URL`` (default ``http://127.0.0.1:8091``).

    Example:
        >>> import inspect
        >>> from thot.tools.okf.app import okf_publish_wiki
        >>> inspect.iscoroutinefunction(okf_publish_wiki)
        True
    """
    ThotMetrics.increment_counter(
        short_name="okf_http",
        method="POST",
        path="/okf/bundles/{bundle_id}/publish-wiki",
        status=200,
    )
    space = _space(authorization)
    store = _store(app)
    bundle = store.get_bundle(bundle_id, space)
    if bundle is None:
        raise _bundle_missing(space, bundle_id)

    root = Path(bundle.path)
    wiki_path = root / "wiki.md"
    if body and body.markdown and body.markdown.strip():
        try:
            store.put_wiki(bundle_id, space, body.markdown)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif not wiki_path.is_file():
        # Backfill for older scoped bundles that only have query_context.
        query = (bundle.query or "").strip() or bundle_id
        qc = root / "query_context.md"
        answer = ""
        if qc.is_file():
            answer = qc.read_text(encoding="utf-8")
        write_llm_wiki(
            root,
            query=query,
            user_space=space,
            rag_payload={"answer": answer},
            concept_ids=store.list_concepts(bundle_id, space),
            bundle_id=bundle_id,
        )
    if not wiki_path.is_file():
        raise HTTPException(
            status_code=404, detail="wiki.md not found in bundle"
        )

    wiki_bytes = wiki_path.read_bytes()
    dest = (
        body.path if body and body.path else None
    ) or suggested_workspace_wiki_path(bundle.query or bundle_id)
    dest = dest.strip().lstrip("/")
    if not dest.lower().endswith(".md"):
        dest = f"{dest}.md"

    ingest_url = os.getenv("INGEST_URL", "http://127.0.0.1:8091").rstrip("/")
    headers: dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    filename = Path(dest).name
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            upload = await client.post(
                f"{ingest_url}/workspace/upload",
                headers=headers,
                files={
                    "file": (filename, wiki_bytes, "text/markdown"),
                },
                data={"path": dest},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"ingest unreachable at {ingest_url}: {exc}",
        ) from exc
    if upload.status_code >= 400:
        detail: Any
        try:
            detail = upload.json()
        except Exception:  # noqa: BLE001
            detail = upload.text
        raise HTTPException(status_code=upload.status_code, detail=detail)

    payload = upload.json() if upload.content else {}
    return {
        "bundle_id": bundle_id,
        "wiki_path": "wiki.md",
        "workspace_path": payload.get("path") or dest,
        "source_ref": payload.get("source_ref"),
        "ingest_id": payload.get("ingest_id"),
        "status": payload.get("status"),
        "user_space": space,
        "index_target": "user",
    }


@app.delete("/okf/bundles/{bundle_id}")
async def okf_bundle_delete(
    bundle_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """DSR / forget: log deletion ActionRecord and remove the bundle.

    Example:
        >>> import inspect
        >>> from thot.tools.okf.app import okf_bundle_delete
        >>> inspect.iscoroutinefunction(okf_bundle_delete)
        True
    """
    space = _space(authorization)
    store = _store(app)
    bundle = store.get_bundle(bundle_id, space)
    if bundle is None:
        raise _bundle_missing(space, bundle_id)
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
        impact=ImpactInfo.model_validate({"class": "destructive"}),
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
    """Run the OKF HTTP service with uvicorn.

    Args:
        argv: Optional CLI arguments (host/port overrides).

    Example:
        >>> import inspect
        >>> from thot.tools.okf.app import main
        >>> callable(main)
        True
    """
    parser = argparse.ArgumentParser(prog="tkeir-okf")
    parser.add_argument("--host", default=os.getenv("OKF_HOST", "0.0.0.0"))
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("OKF_PORT", "8095"))
    )
    args = parser.parse_args(argv)
    import uvicorn

    uvicorn.run(
        "thot.tools.okf.app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
