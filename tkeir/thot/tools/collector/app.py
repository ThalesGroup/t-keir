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
from fastapi import FastAPI, HTTPException, Request
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
    from thot.tools.collector.forge_config import (
        clear_forge_config_cache,
        ensure_workspace_forge_config,
        load_forge_config,
    )
    from thot.tools.collector.quality import (
        bundled_osint_sources_path,
        clear_osint_sources_cache,
        load_osint_sources,
        workspace_osint_sources_path,
    )
    from thot.tools.collector.service import load_dedupe_index

    configure_json_logging(
        service=os.getenv("TKEIR_SERVICE", "tkeir-collector")
    )
    _ensure_collector_metrics()
    settings = collector_settings()
    # Seed workspace allowlist from bundled default when missing.
    ws_sources = workspace_osint_sources_path(settings.workspace)
    if not ws_sources.is_file():
        bundled = bundled_osint_sources_path()
        if bundled.is_file():
            ws_sources.parent.mkdir(parents=True, exist_ok=True)
            ws_sources.write_text(
                bundled.read_text(encoding="utf-8"), encoding="utf-8"
            )
            log_structured(
                "info",
                "seeded OSINT allowlist",
                service=SERVICE_NAME,
                path=str(ws_sources),
            )
    clear_osint_sources_cache()
    allow_enabled, allow_hosts, allow_path = load_osint_sources()
    forge_path = ensure_workspace_forge_config(settings.workspace)
    clear_forge_config_cache()
    forge_cfg = load_forge_config()
    state = AppState(settings)
    log_structured(
        "info",
        "collector starting",
        service=SERVICE_NAME,
        searxng_url=settings.searxng_url,
        port=settings.port,
        simhash_max_hamming=settings.simhash_max_hamming,
        osint_sources_path=allow_path,
        osint_allowlist_enabled=allow_enabled,
        osint_allowlist_hosts=len(allow_hosts),
        forge_config=str(forge_path),
        forge_save_queries=forge_cfg.save_queries,
        forge_nlp_enabled=forge_cfg.nlp.enabled,
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
    # Optional background wiki loop (default: disabled via interval=0).
    # Per-feed wiki always uses tkeir-agent (AGENT_URL) from best golden chunks.
    from thot.tools.collector.wiki_loop import WIKI_LOOP

    WIKI_LOOP.agent_url = settings.agent_url
    if settings.wiki_enabled and settings.wiki_interval_s > 0:
        WIKI_LOOP.start(settings.wiki_interval_s)
        log_structured(
            "info",
            "wiki loop started",
            service=SERVICE_NAME,
            interval_s=settings.wiki_interval_s,
            agent_url=settings.agent_url,
        )
    try:
        yield
    finally:
        WIKI_LOOP.stop()
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
    categories: str | None = Field(
        default=None,
        description="SearXNG categories (default: general,news,science)",
    )
    engines: str | None = Field(
        default=None,
        description="Comma-separated SearXNG engine names",
    )
    safesearch: int | None = Field(
        default=None, ge=0, le=2, description="0 off / 1 moderate / 2 strict"
    )
    time_range: str | None = Field(
        default=None, description="day | week | month | year"
    )


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
    categories: str | None = None
    engines: str | None = None
    safesearch: int | None = Field(default=None, ge=0, le=2)
    time_range: str | None = None


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


@app.get("/status")
async def pipeline_status(probe_agent: bool = True) -> dict[str, Any]:
    """
    Live pipeline phase + ETA (optionally probes wiki agent run).

        Osiris should poll this during READ / wiki produce.

        Example:
            >>> True
            True
    """
    from thot.tools.collector.pipeline_status import PIPELINE_STATUS
    from thot.tools.collector.wiki_loop import WIKI_LOOP

    snap = PIPELINE_STATUS.snapshot(probe_agent=bool(probe_agent))
    wiki = WIKI_LOOP.snapshot()
    snap["wiki"] = {
        "status": wiki.get("status"),
        "producing": wiki.get("producing"),
        "wiki_ready": wiki.get("wiki_ready"),
        "iteration": wiki.get("iteration"),
        "run_id": wiki.get("run_id"),
        "markdown_chars": len(str(wiki.get("markdown") or "")),
        "sources": len(wiki.get("sources") or []),
    }
    if wiki.get("run_id") and not snap.get("run_id"):
        snap["run_id"] = wiki.get("run_id")
    return snap


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
            categories=body.categories,
            engines=body.engines,
            safesearch=body.safesearch,
            time_range=body.time_range,
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


class FeedRequest(BaseModel):
    """POST /feed — optional Osiris data / pre-forged queries."""

    data: dict[str, Any] | None = None
    queries: list[dict[str, Any]] | None = None
    max_queries: int = Field(default=40, ge=1, le=50)
    max_results_per_query: int | None = Field(default=None, ge=1, le=25)
    map_center: dict[str, float] | None = None
    produce_wiki: bool = True
    # Osiris specialized business ontology (external BO for NLP annotate).
    business_ontology: dict[str, Any] | list[Any] | None = None
    business_ontology_yaml: str | None = None


class WikiStartRequest(BaseModel):
    """POST /wiki/start — enable iterative wiki loop."""

    interval_s: int = Field(default=120, ge=0, le=86400)
    topic: str | None = None


class WikiProduceRequest(BaseModel):
    """POST /wiki — one-shot wiki with optional Osiris business ontology."""

    topic: str | None = None
    business_ontology: dict[str, Any] | list[Any] | None = None
    business_ontology_yaml: str | None = None


async def _run_feed(
    *,
    data: dict[str, Any] | None = None,
    queries: list[dict[str, Any]] | None = None,
    max_queries: int = 40,
    max_results_per_query: int | None = None,
    map_center: dict[str, float] | None = None,
    produce_wiki: bool = True,
    business_ontology: Any = None,
    business_ontology_yaml: str | None = None,
) -> dict[str, Any]:
    """
    User-triggered feed; wiki always via agent from best golden chunks.

        Example:
            >>> True
            True
    """
    from thot.tools.collector.feed import build_feed
    from thot.tools.collector.wiki_loop import WIKI_LOOP

    state = _state()
    WIKI_LOOP.agent_url = state.settings.agent_url
    feed = await build_feed(
        state.settings,
        data=data,
        queries=queries,
        max_queries=max_queries,
        max_results_per_query=max_results_per_query,
        map_center=map_center,
        dedupe=state.dedupe,
        include_wiki=True,
        wiki_state=None,
    )
    if produce_wiki and feed.get("documents"):
        wiki_snap = await WIKI_LOOP.produce_once(
            list(feed.get("documents") or []),
            topic="osiris-live",
            agent_url=state.settings.agent_url,
            business_ontology=business_ontology,
            business_ontology_yaml=business_ontology_yaml,
            osiris_base_url=state.settings.osiris_base_url,
        )
        feed["wiki"] = wiki_snap
    else:
        snap = WIKI_LOOP.snapshot()
        feed["wiki"] = snap if (snap.get("markdown") or "").strip() else None
    return feed


@app.get("/feed")
async def feed_get(
    max_queries: int = 40,
    hits: int = 5,
    lat: float | None = None,
    lng: float | None = None,
    produce_wiki: bool = True,
) -> dict[str, Any]:
    """
    User-triggered: Osiris → forge → SearXNG → markdown + agent wiki.

        Example:
            >>> True
            True
    """
    center = (
        {"lat": lat, "lng": lng}
        if lat is not None and lng is not None
        else None
    )
    try:
        return await _run_feed(
            max_queries=max_queries,
            max_results_per_query=hits,
            map_center=center,
            produce_wiki=produce_wiki,
        )
    except Exception as exc:  # noqa: BLE001
        log_structured(
            "error",
            "feed failed",
            service=SERVICE_NAME,
            path="/feed",
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/feed")
async def feed_post(body: FeedRequest) -> dict[str, Any]:
    """
    Same as GET /feed with optional ``data`` / ``queries`` body.

        Example:
            >>> True
            True
    """
    try:
        return await _run_feed(
            data=body.data,
            queries=body.queries,
            max_queries=body.max_queries,
            max_results_per_query=body.max_results_per_query,
            map_center=body.map_center,
            produce_wiki=body.produce_wiki,
            business_ontology=body.business_ontology,
            business_ontology_yaml=body.business_ontology_yaml,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/wiki")
async def wiki_get() -> dict[str, Any]:
    """
    Latest live wiki snapshot produced by the collector.

        Example:
            >>> True
            True
    """
    from thot.tools.collector.wiki_loop import WIKI_LOOP

    return WIKI_LOOP.snapshot()


@app.post("/wiki")
async def wiki_post(request: Request) -> dict[str, Any]:
    """
    Produce wiki from last feed documents (sources kept).

        Body ``async: true`` (default) enqueues background production and returns
        immediately with ``status=producing`` — poll ``GET /wiki`` until done.
        Set ``async: false`` for a blocking wait (may exceed proxy timeouts).

        Example:
            >>> True
            True
    """
    from thot.tools.collector.feed import get_last_feed
    from thot.tools.collector.wiki_loop import WIKI_LOOP

    state = _state()
    WIKI_LOOP.agent_url = state.settings.agent_url
    body_data: dict[str, Any] = {}
    try:
        body_data = await request.json()
        if not isinstance(body_data, dict):
            body_data = {}
    except Exception:  # noqa: BLE001
        body_data = {}
    topic = (
        str(
            body_data.get("topic") or request.query_params.get("topic") or ""
        ).strip()
        or "osiris-live"
    )
    business_ontology = body_data.get("business_ontology")
    business_ontology_yaml = body_data.get("business_ontology_yaml")
    if isinstance(business_ontology_yaml, (bytes, bytearray)):
        business_ontology_yaml = business_ontology_yaml.decode(
            "utf-8", "replace"
        )
    if business_ontology_yaml is not None:
        business_ontology_yaml = str(business_ontology_yaml)

    async_mode = body_data.get("async", body_data.get("async_mode", True))
    if isinstance(async_mode, str):
        async_mode = async_mode.strip().lower() not in {"0", "false", "no"}
    else:
        async_mode = bool(async_mode)

    feed = get_last_feed() or {}
    docs = list(feed.get("documents") or [])
    if not docs:
        if async_mode:
            # Never block the HTTP response on a full feed rebuild — that was
            # reintroducing the Next.js ~5min "fetch failed" on wiki enqueue.
            raise HTTPException(
                status_code=400,
                detail="No collected documents — run GET/POST /feed first (produce_wiki=false), then POST /wiki",
            )
        built = await _run_feed(
            max_queries=40,
            max_results_per_query=3,
            produce_wiki=False,
            business_ontology=business_ontology,
            business_ontology_yaml=business_ontology_yaml,
        )
        docs = list(built.get("documents") or [])
    if not docs:
        raise HTTPException(
            status_code=400,
            detail="No collected documents — run GET /feed first",
        )

    kwargs = {
        "topic": topic,
        "agent_url": state.settings.agent_url,
        "business_ontology": business_ontology,
        "business_ontology_yaml": business_ontology_yaml,
        "osiris_base_url": state.settings.osiris_base_url,
    }
    if async_mode:
        return WIKI_LOOP.enqueue_produce(docs, **kwargs)
    return await WIKI_LOOP.produce_once(docs, **kwargs)


@app.post("/wiki/start")
async def wiki_start(body: WikiStartRequest) -> dict[str, Any]:
    """
    Start iterative wiki updates every ``interval_s`` (0 = stop).

        Example:
            >>> True
            True
    """
    from thot.tools.collector.wiki_loop import WIKI_LOOP

    if body.interval_s <= 0:
        return WIKI_LOOP.stop()
    snap = WIKI_LOOP.start(body.interval_s)
    # Kick an immediate iteration when feed exists.
    from thot.tools.collector.feed import get_last_feed

    feed = get_last_feed() or {}
    docs = list(feed.get("documents") or [])
    if docs:
        await WIKI_LOOP.produce_once(docs, topic=body.topic or "osiris-live")
        snap = WIKI_LOOP.snapshot()
    return snap


@app.post("/wiki/stop")
async def wiki_stop() -> dict[str, Any]:
    """
    Stop the iterative wiki loop.

        Example:
            >>> True
            True
    """
    from thot.tools.collector.wiki_loop import WIKI_LOOP

    return WIKI_LOOP.stop()


@app.get("/wiki/saved")
async def wiki_saved_latest() -> dict[str, Any]:
    """
    Return the latest dated wiki panel bundle (wiki + queries + docs…).

        Example:
            >>> True
            True
    """
    from thot.tools.collector.wiki_store import load_wiki_bundle

    bundle = load_wiki_bundle(_state().settings.workspace, None)
    if not bundle:
        raise HTTPException(status_code=404, detail="No saved wiki yet")
    return bundle


@app.get("/wiki/saved/list")
async def wiki_saved_list(limit: int = 50) -> dict[str, Any]:
    """
    List saved wiki bundles newest-first.

        Example:
            >>> True
            True
    """
    from thot.tools.collector.wiki_store import list_wiki_bundles

    rows = list_wiki_bundles(
        _state().settings.workspace,
        limit=max(1, min(200, int(limit or 50))),
    )
    return {"ok": True, "count": len(rows), "bundles": rows}


@app.get("/wiki/saved/{bundle_id}")
async def wiki_saved_get(bundle_id: str) -> dict[str, Any]:
    """
    Return one saved wiki panel bundle by id (or ``latest``).

        Example:
            >>> True
            True
    """
    from thot.tools.collector.wiki_store import load_wiki_bundle

    bundle = load_wiki_bundle(_state().settings.workspace, bundle_id)
    if not bundle:
        raise HTTPException(
            status_code=404, detail=f"Wiki bundle not found: {bundle_id}"
        )
    return bundle


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
