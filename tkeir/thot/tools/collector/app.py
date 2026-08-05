"""Title: Web collector FastAPI service (SearXNG → markdown documents).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from thot import __version__ as TKEIR_VERSION
from thot.action.correlation import current_correlation_id
from thot.action.middleware import ActionCorrelationMiddleware
from thot.action.models import new_action_id
from thot.core.StructuredLogging import configure_json_logging, log_structured
from thot.core.ThotMetrics import ThotMetrics
from thot.governor.wiring import wire_governor_middleware
from thot.tools.collector.config import CollectorSettings, collector_settings
from thot.tools.collector.dedupe import CollectorDedupeIndex
from thot.tools.collector.service import (
    collect_markdown,
    collect_queries_batch,
    wrap_collect_results,
)

LOGGER = logging.getLogger(__name__)
SERVICE_NAME = os.getenv("TKEIR_SERVICE", "tkeir-collector")


class AppState:
    """Collector process state.

    Example:
        >>> from thot.tools.collector.app import AppState
        >>> from thot.tools.collector.config import collector_settings
        >>> AppState(settings=collector_settings()).dedupe is None
        True
    """

    def __init__(self, settings: CollectorSettings) -> None:
        """Attach settings; dedupe index loaded in lifespan.

        Example:
            >>> from thot.tools.collector.config import collector_settings
            >>> st = AppState(collector_settings())
            >>> st.settings.port > 0
            True
        """
        self.settings = settings
        self.dedupe: CollectorDedupeIndex | None = None


def _ensure_collector_metrics() -> None:
    """Register collector OpenTelemetry counters (idempotent).

    Example:
        >>> from thot.tools.collector.app import _ensure_collector_metrics
        >>> _ensure_collector_metrics()
        >>> from thot.core.ThotMetrics import ThotMetrics
        >>> "collector_http" in ThotMetrics.call_counter
        True
    """
    ThotMetrics.create_counter(
        short_name="collector_http",
        function_name="tkeir_collector_http_requests_total",
        counter_description="Collector HTTP requests observed",
    )
    ThotMetrics.create_counter(
        short_name="collector_documents",
        function_name="tkeir_collector_documents_total",
        counter_description="Collector markdown documents returned after dedupe",
    )
    ThotMetrics.create_counter(
        short_name="collector_duplicates",
        function_name="tkeir_collector_duplicates_total",
        counter_description="Collector near-duplicates skipped (URL/SimHash)",
    )
    ThotMetrics.create_counter(
        short_name="collector_errors",
        function_name="tkeir_collector_errors_total",
        counter_description="Collector per-URL fetch/convert errors",
    )


def _record_collect_outcome(
    path: str, result: dict[str, Any], *, status: int
) -> None:
    """Increment domain counters and emit a structured completion log.

    ``result`` is the public collect table: ``{"results": [<per-query row>, ...]}``.

    Example:
        >>> from thot.tools.collector.app import _record_collect_outcome
        >>> _ensure_collector_metrics()
        >>> _record_collect_outcome(
        ...     "/collect",
        ...     {"results": [{"documents": [], "duplicates": [], "errors": []}]},
        ...     status=200,
        ... )
    """
    _ensure_collector_metrics()
    ThotMetrics.increment_counter(
        short_name="collector_http",
        method="POST",
        path=path,
        status=status,
    )
    rows = result.get("results") or []
    n_docs = n_dups = n_errs = 0
    correlation_id = current_correlation_id()
    dedupe_index_size = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if correlation_id is None:
            correlation_id = row.get("correlation_id")
        if dedupe_index_size is None:
            dedupe_index_size = (row.get("dedupe") or {}).get("index_size")
        n_docs += len(row.get("documents") or [])
        n_dups += len(row.get("duplicates") or [])
        n_errs += len(row.get("errors") or [])
    for _ in range(n_docs):
        ThotMetrics.increment_counter(
            short_name="collector_documents",
            method="POST",
            path=path,
            status=status,
        )
    for _ in range(n_dups):
        ThotMetrics.increment_counter(
            short_name="collector_duplicates",
            method="POST",
            path=path,
            status=status,
        )
    for _ in range(n_errs):
        ThotMetrics.increment_counter(
            short_name="collector_errors",
            method="POST",
            path=path,
            status=status,
        )
    log_structured(
        "info",
        "collect completed",
        service=SERVICE_NAME,
        correlation_id=correlation_id,
        path=path,
        documents=n_docs,
        duplicates=n_dups,
        errors=n_errs,
        query_count=len(rows),
        dedupe_index_size=dedupe_index_size,
        status=status,
    )


def _correlation_id() -> str:
    """Return the current action correlation id or allocate a new one.

    Example:
        >>> len(_correlation_id()) > 0
        True
    """
    return current_correlation_id() or new_action_id()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load JSON logging, metrics, and SimHash index.

    Example:
        >>> import inspect
        >>> from thot.tools.collector.app import lifespan
        >>> inspect.isasyncgenfunction(lifespan.__wrapped__)
        True
    """
    from thot.tools.collector.service import load_dedupe_index

    configure_json_logging(
        service=os.getenv("TKEIR_SERVICE", "tkeir-collector")
    )
    _ensure_collector_metrics()
    settings = collector_settings()
    state = AppState(settings)
    log_structured(
        "info",
        "collector starting",
        service=SERVICE_NAME,
        searxng_url=settings.searxng_url,
        port=settings.port,
        simhash_max_hamming=settings.simhash_max_hamming,
    )
    state.dedupe = load_dedupe_index(settings)
    log_structured(
        "info",
        "collector ready",
        service=SERVICE_NAME,
        dedupe_index_size=state.dedupe.size,
        dedupe_path=str(state.dedupe.path),
    )
    app.state.collector = state
    try:
        yield
    finally:
        app.state.collector = None


app = FastAPI(
    title="T-KEIR Web Collector",
    version=TKEIR_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "COLLECTOR_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    ActionCorrelationMiddleware,
    service=os.getenv("TKEIR_SERVICE", "tkeir-collector"),
)
wire_governor_middleware(
    app, service=os.getenv("TKEIR_SERVICE", "tkeir-collector")
)


class CollectRequest(BaseModel):
    """POST /collect body.

    Example:
        >>> CollectRequest(query="maritime AIS").query
        'maritime AIS'
    """

    query: str = Field(..., min_length=1)
    topic: str | None = Field(
        default=None,
        description="Optional topic label stamped into markdown front matter",
    )
    max_results: int | None = Field(default=None, ge=1, le=25)
    language: str | None = None


class CollectQueryItem(BaseModel):
    """One query inside a multi-collect batch.

    Example:
        >>> CollectQueryItem(query="AIS spoofing").query
        'AIS spoofing'
    """

    query: str = Field(..., min_length=1)
    topic: str | None = None
    max_results: int | None = Field(default=None, ge=1, le=25)
    language: str | None = None


class CollectBatchRequest(BaseModel):
    """POST /collect/batch body — several queries in parallel.

    Example:
        >>> CollectBatchRequest(queries=[CollectQueryItem(query="a")]).query_count
        1
    """

    queries: list[CollectQueryItem] = Field(..., min_length=1, max_length=50)
    concurrency: int | None = Field(default=None, ge=1, le=16)

    @property
    def query_count(self) -> int:
        """Number of queries in the batch.

        Example:
            >>> CollectBatchRequest(queries=[CollectQueryItem(query="x")]).query_count
            1
        """
        return len(self.queries)


def _state(application: FastAPI = app) -> AppState:
    """Return collector AppState or raise 503.

    Example:
        >>> from fastapi import FastAPI
        >>> from thot.tools.collector.app import _state
        >>> try:
        ...     _state(FastAPI())
        ... except Exception as exc:
        ...     getattr(exc, "status_code", None)
        503
    """
    state = getattr(application.state, "collector", None)
    if state is None:
        raise HTTPException(status_code=503, detail="collector not ready")
    return state


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe.

    Example:
        >>> import inspect
        >>> from thot.tools.collector.app import health
        >>> inspect.iscoroutinefunction(health)
        True
    """
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    """Readiness: dedupe loaded + SearXNG reachable.

    Example:
        >>> import inspect
        >>> from thot.tools.collector.app import ready
        >>> inspect.iscoroutinefunction(ready)
        True
    """
    state = _state()
    searx_ok = False
    detail = ""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{state.settings.searxng_url}/healthz"
            )
            searx_ok = response.status_code < 500
            detail = f"status={response.status_code}"
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)
    if state.dedupe is None or not searx_ok:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "dedupe": state.dedupe is not None,
                "searxng": searx_ok,
                "searxng_detail": detail,
            },
        )
    return {
        "status": "ready",
        "searxng": True,
        "searxng_url": state.settings.searxng_url,
        "dedupe_index_size": state.dedupe.size,
    }


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus exposition (OpenTelemetry → Prometheus).

    Example:
        >>> import inspect
        >>> from thot.tools.collector.app import metrics
        >>> inspect.iscoroutinefunction(metrics)
        True
    """
    _ensure_collector_metrics()
    payload = ThotMetrics.generateMetricsResponse()
    return Response(
        content=payload,
        media_type=getattr(
            ThotMetrics,
            "METRIC_MIME_TYPE",
            "text/plain; version=0.0.4; charset=utf-8",
        ),
    )


@app.get("/dedupe")
async def dedupe_stats() -> dict[str, Any]:
    """Return SimHash / URL dedupe index stats.

    Example:
        >>> import inspect
        >>> from thot.tools.collector.app import dedupe_stats
        >>> inspect.iscoroutinefunction(dedupe_stats)
        True
    """
    state = _state()
    if state.dedupe is None:
        raise HTTPException(status_code=503, detail="dedupe index not loaded")
    return {
        "index_size": state.dedupe.size,
        "max_hamming": state.dedupe.max_hamming,
        "path": str(state.dedupe.path),
    }


@app.post("/collect")
async def collect(body: CollectRequest) -> dict[str, Any]:
    """Search SearXNG, fetch pages, return ``{"results": [<one query row>]}``.

    Near-duplicates are skipped via the shared SimHash index. Documents are
    returned in the JSON body only (not persisted). Does not run the NLP
    pipeline. Emits audit ActionRecords via middleware and metrics.

    Example:
        >>> import inspect
        >>> from thot.tools.collector.app import collect
        >>> inspect.iscoroutinefunction(collect)
        True
    """
    state = _state()
    try:
        row = await collect_markdown(
            state.settings,
            query=body.query,
            topic=body.topic,
            max_results=body.max_results,
            language=body.language,
            dedupe=state.dedupe,
            correlation_id=_correlation_id(),
        )
        result = wrap_collect_results([row])
        _record_collect_outcome("/collect", result, status=200)
        return result
    except Exception as exc:  # noqa: BLE001
        log_structured(
            "error",
            "collect failed",
            service=SERVICE_NAME,
            correlation_id=current_correlation_id(),
            path="/collect",
            error=str(exc),
        )
        ThotMetrics.increment_counter(
            short_name="collector_http",
            method="POST",
            path="/collect",
            status=502,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/collect/batch")
async def collect_batch(body: CollectBatchRequest) -> dict[str, Any]:
    """Collect several queries; return ``{"results": [<row per query>, ...]}``.

    Example:
        >>> import inspect
        >>> from thot.tools.collector.app import collect_batch
        >>> inspect.iscoroutinefunction(collect_batch)
        True
    """
    state = _state()
    try:
        result = await collect_queries_batch(
            state.settings,
            queries=[item.model_dump() for item in body.queries],
            dedupe=state.dedupe,
            concurrency=body.concurrency,
            correlation_id=_correlation_id(),
        )
        _record_collect_outcome("/collect/batch", result, status=200)
        return result
    except ValueError as exc:
        ThotMetrics.increment_counter(
            short_name="collector_http",
            method="POST",
            path="/collect/batch",
            status=400,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_structured(
            "error",
            "collect/batch failed",
            service=SERVICE_NAME,
            correlation_id=current_correlation_id(),
            path="/collect/batch",
            error=str(exc),
        )
        ThotMetrics.increment_counter(
            short_name="collector_http",
            method="POST",
            path="/collect/batch",
            status=502,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def main() -> None:
    """CLI entry: ``tkeir-collector``.

    Example:
        >>> from thot.tools.collector.app import main
        >>> callable(main)
        True
    """
    import uvicorn

    from thot.core.StructuredLogging import configure_text_logging

    settings = collector_settings()
    configure_text_logging(level=logging.INFO, force=True)
    uvicorn.run(
        "thot.tools.collector.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
