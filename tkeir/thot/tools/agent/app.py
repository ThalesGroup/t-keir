"""Title: Agent FastAPI service (``tkeir-agent`` on :8092).

HTTP tool surface for single-agent loops and Phase D workflows.
Library agents live in ``thot.agent`` (:class:`~thot.agent.agent.Agent` /
:class:`~thot.agent.agent.AgentSet`).

Run with ``python -m thot.tools.agent`` or the ``tkeir-agent`` entry point.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from thot import __version__ as TKEIR_VERSION
from thot.action.correlation import (
    current_correlation_id,
    generate_trace_id,
)
from thot.action.middleware import ActionCorrelationMiddleware
from thot.action.models import utc_now_rfc3339
from thot.agent.agent import AgentSet
from thot.agent.guard import AgentGuard
from thot.agent.llm_agent import LLMAgent
from thot.agent.models import RunState
from thot.agent.orchestrator import Orchestrator
from thot.agent.paths import default_agent_root
from thot.agent.publish import publish_run
from thot.agent.runs import RunStore
from thot.agent.spiffe import (
    is_allowed_agent_spiffe_id,
    resolve_agent_spiffe_id,
    spiffe_enforce,
)
from thot.agent.workflows import list_workflow_names, load_workflow
from thot.compose.registry import list_template_names, load_template
from thot.core.LlmWrapper import UnifiedLLMWrapper
from thot.core.StructuredLogging import configure_json_logging
from thot.core.ThotMetrics import ThotMetrics
from thot.mcp.client import default_outbound_client
from thot.tools.search.user_space import resolve_vespa_user_space

LOGGER = logging.getLogger(__name__)

# Process-wide config set (overridden by ``main()`` / tests via ``configure_agents``).
_AGENT_SET: AgentSet | None = None


def configure_agents(
    agent_set: AgentSet | None = None,
    *,
    config_dirs: list[Path | str] | None = None,
    names: list[str] | None = None,
) -> AgentSet:
    """Install the agent configuration set used by this process.

    Args:
        agent_set: Pre-built set; when set, ``config_dirs`` / ``names`` ignored.
        config_dirs: Extra/override agent YAML roots (passed to
            :meth:`AgentSet.from_default` when ``agent_set`` is omitted).
        names: Optional allow-list of agent stems.

    Returns:
        The active :class:`AgentSet`.

    Example:
        >>> from thot.agent.agent import AgentSet
        >>> from thot.tools.agent.app import configure_agents
        >>> s = configure_agents(AgentSet.from_default(names=["researcher"]))
        >>> "researcher" in s
        True
    """
    global _AGENT_SET
    if agent_set is not None:
        _AGENT_SET = agent_set
    else:
        _AGENT_SET = AgentSet.from_default(names=names, extra_dirs=config_dirs)
    return _AGENT_SET


def get_agent_set() -> AgentSet:
    """Return the process agent set, loading defaults on first use.

    Example:
        >>> from thot.tools.agent.app import get_agent_set
        >>> isinstance(get_agent_set(), AgentSet)
        True
    """
    global _AGENT_SET
    if _AGENT_SET is None:
        _AGENT_SET = AgentSet.from_default()
    return _AGENT_SET


def _resolve_space(authorization: str | None) -> str:
    """Map Bearer JWT claims to a Vespa user-space.

    Args:
        authorization: Optional ``Authorization`` header.

    Returns:
        Normalized user-space string.

    Example:
        >>> from thot.tools.agent.app import _resolve_space
        >>> _resolve_space(None)
        'dev@tkeir'
    """
    return resolve_vespa_user_space(authorization)


def _stamp_action_log(request: Request, **fields: Any) -> None:
    """Attach structured fields for the middleware ``request completed`` log.

    Args:
        request: Current FastAPI/Starlette request.
        **fields: Agent/run metadata (``agent``, ``run_id``, ``spiffe_id``, …).

    Example:
        >>> from starlette.requests import Request
        >>> from thot.tools.agent.app import _stamp_action_log
        >>> scope = {
        ...     "type": "http",
        ...     "asgi": {"version": "3.0"},
        ...     "http_version": "1.1",
        ...     "method": "GET",
        ...     "path": "/",
        ...     "raw_path": b"/",
        ...     "query_string": b"",
        ...     "headers": [],
        ...     "client": ("127.0.0.1", 0),
        ...     "server": ("127.0.0.1", 80),
        ...     "scheme": "http",
        ... }
        >>> req = Request(scope)
        >>> _stamp_action_log(req, agent="researcher", run_id="r1")
        >>> req.state.action_log["agent"]
        'researcher'
    """
    existing = getattr(request.state, "action_log", None)
    payload = dict(existing) if isinstance(existing, dict) else {}
    for key, value in fields.items():
        if value is None or value == "":
            continue
        payload[key] = value
    request.state.action_log = payload


class AppState:
    """Per-process agent service state attached to ``FastAPI.state.agent``."""

    def __init__(self, agent_set: AgentSet | None = None) -> None:
        """Initialize run store, guard, LLM placeholder, MCP client, agents.

        Example:
            >>> from thot.tools.agent.app import AppState
            >>> from thot.agent.runs import RunStore
            >>> isinstance(AppState().store, RunStore)
            True
        """
        root = default_agent_root()
        self.root = root
        self.store = RunStore(root)
        gov_root = Path(
            os.getenv("GOVERNOR_STATE_ROOT", str(root / "governor"))
        )
        self.guard = AgentGuard(gov_root)
        self.llm: Any = None
        self.outbound = default_outbound_client()
        self.agents = agent_set or get_agent_set()
        self._tasks: set[asyncio.Task[Any]] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Configure logging, LLM, and ``AppState`` at startup.

    Args:
        app: FastAPI application instance.

    Example:
        >>> import inspect
        >>> from thot.tools.agent.app import lifespan
        >>> inspect.isasyncgenfunction(lifespan.__wrapped__)
        True
    """
    configure_json_logging(service=os.getenv("TKEIR_SERVICE", "tkeir-agent"))
    state = AppState(agent_set=get_agent_set())
    state.store.ensure_layout()
    state.llm = UnifiedLLMWrapper()
    app.state.agent = state
    ThotMetrics.create_counter(
        short_name="agent_http",
        function_name="agent_http_requests_total",
        counter_description="Agent HTTP requests",
    )
    yield


app = FastAPI(
    title="T-KEIR Agent",
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
app.add_middleware(ActionCorrelationMiddleware)


class CreateRunBody(BaseModel):
    agent: str = "researcher"
    workflow: str | None = None
    goal: str
    params: dict[str, Any] = Field(default_factory=dict)
    template: str | None = None


async def _execute_run(
    app_state: AppState,
    run_id: str,
    authorization: str | None,
) -> None:
    """Background task: run workflow or single-agent loop for ``run_id``.

    Args:
        app_state: Shared service state (store, guard, LLM, agent set).
        run_id: Persisted run identifier.
        authorization: Optional Bearer token for tool calls.

    Example:
        >>> import inspect
        >>> from thot.tools.agent.app import _execute_run
        >>> inspect.iscoroutinefunction(_execute_run)
        True
    """
    state = app_state.store.read_state(run_id)
    if state is None:
        return
    try:
        if state.workflow:
            workflow = load_workflow(state.workflow)
            orch = Orchestrator(
                store=app_state.store,
                guard=app_state.guard,
                llm=app_state.llm,
                outbound=app_state.outbound,
            )
            await orch.run(state, workflow, authorization=authorization)
            return
        try:
            spec = app_state.agents.load_spec(state.agent)
        except KeyError as exc:
            raise FileNotFoundError(str(exc)) from exc
        # General-purpose LLMAgent (wiki-agnostic) wraps AgentLoop.
        agent = LLMAgent(
            store=app_state.store,
            guard=app_state.guard,
            llm=app_state.llm,
            spec=spec,
        )
        await agent.run(
            state,
            identity_context=state.spiffe_id,
            state=state,
            spec=spec,
            authorization=authorization,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("agent run %s crashed", run_id)
        state = app_state.store.read_state(run_id) or state
        state.status = "failed"
        state.error = str(exc)
        state.ended_at = utc_now_rfc3339()
        app_state.store.write_state(state)
        app_state.store.move_to_dlq(run_id, str(exc))


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe.

    Example:
        >>> import inspect
        >>> from thot.tools.agent.app import health
        >>> inspect.iscoroutinefunction(health)
        True
    """
    return {"status": "ok", "service": "tkeir-agent"}


@app.get("/ready")
async def ready(request: Request) -> dict[str, Any]:
    """Readiness probe with agent registry and SPIFFE metadata.

    Example:
        >>> import inspect
        >>> from thot.tools.agent.app import ready
        >>> inspect.iscoroutinefunction(ready)
        True
    """
    state: AppState = request.app.state.agent
    workload_id = resolve_agent_spiffe_id("tkeir-agent")
    return {
        "status": "ready",
        "agents": state.agents.names(),
        "workflows": list_workflow_names(),
        "config_dirs": [str(p) for p in state.agents.config_dirs],
        "root": str(state.root),
        "spiffe_id": workload_id,
        "spiffe_enforce": spiffe_enforce(),
    }


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics exposition endpoint.

    Example:
        >>> import inspect
        >>> from thot.tools.agent.app import metrics
        >>> inspect.iscoroutinefunction(metrics)
        True
    """
    payload = ThotMetrics.generateMetricsResponse()
    return Response(content=payload, media_type=ThotMetrics.METRIC_MIME_TYPE)


@app.get("/agent/agents")
async def agents(request: Request, wiki: bool = False) -> dict[str, Any]:
    """List configured agents with catalog metadata.

    Query ``wiki=true`` to return only wiki-capable ``*_prompt`` agents.
    The set is the configuration bundle this service process was started with.

    Example:
        >>> import inspect
        >>> from thot.tools.agent.app import agents
        >>> inspect.iscoroutinefunction(agents)
        True
    """
    state: AppState = request.app.state.agent
    catalog = state.agents.catalog(wiki_only=bool(wiki))
    return {
        "agents": [e["name"] for e in catalog],
        "catalog": catalog,
        "config_dirs": [str(p) for p in state.agents.config_dirs],
        "config_dirs_env": "TKEIR_AGENT_CONFIG_DIRS",
    }


@app.get("/agent/agents/{agent_name}")
async def agent_detail(agent_name: str, request: Request) -> dict[str, Any]:
    """Return catalog metadata for one agent in this service's set.

    Example:
        >>> import inspect
        >>> from thot.tools.agent.app import agent_detail
        >>> inspect.iscoroutinefunction(agent_detail)
        True
    """
    state: AppState = request.app.state.agent
    try:
        return state.agents.get(agent_name).catalog_entry()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/agent/templates")
async def templates() -> dict[str, Any]:
    """List compose answer/report template names (OTAN forms, etc.).

    Example:
        >>> import inspect
        >>> from thot.tools.agent.app import templates
        >>> inspect.iscoroutinefunction(templates)
        True
    """
    names = list_template_names()
    catalog: list[dict[str, Any]] = []
    for name in names:
        try:
            spec = load_template(name)
        except (OSError, ValueError, FileNotFoundError):
            catalog.append({"name": name})
            continue
        catalog.append(
            {
                "name": spec.name,
                "version": getattr(spec, "version", 1),
                "title": getattr(spec, "title", "") or "",
                "description": (getattr(spec, "description", "") or "")[:240],
                "slot_count": len(getattr(spec, "slots", []) or []),
            }
        )
    return {"templates": names, "catalog": catalog}


@app.get("/agent/workflows")
async def workflows() -> dict[str, Any]:
    """List configured workflow spec names.

    Example:
        >>> import inspect
        >>> from thot.tools.agent.app import workflows
        >>> inspect.iscoroutinefunction(workflows)
        True
    """
    return {"workflows": list_workflow_names()}


@app.post("/agent/runs")
async def create_run(
    body: CreateRunBody,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Enqueue an async agent or workflow run.

    Example:
        >>> import inspect
        >>> from thot.tools.agent.app import create_run
        >>> inspect.iscoroutinefunction(create_run)
        True
    """
    app_state: AppState = request.app.state.agent
    if body.workflow:
        try:
            load_workflow(body.workflow)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    else:
        if body.agent not in app_state.agents:
            raise HTTPException(
                status_code=404,
                detail=f"agent not in service configuration: {body.agent!r}",
            )

    cid = current_correlation_id() or generate_trace_id()
    space = _resolve_space(authorization)
    agent_name = body.agent if not body.workflow else "supervisor"
    spiffe_id = resolve_agent_spiffe_id(agent_name)
    if spiffe_enforce() and not is_allowed_agent_spiffe_id(spiffe_id):
        raise HTTPException(
            status_code=403,
            detail=(
                "agent SPIFFE identity missing or not allowed "
                f"(spiffe_id={spiffe_id!r})"
            ),
        )
    params = dict(body.params)
    if body.template:
        params.setdefault("template", body.template)
    run = RunState(
        agent=agent_name,
        workflow=body.workflow,
        goal=body.goal.strip(),
        user_space=space,
        spiffe_id=spiffe_id,
        correlation_id=cid,
        status="queued",
        params=params,
    )
    if not run.goal:
        raise HTTPException(status_code=400, detail="goal is required")
    app_state.store.write_state(run)

    async def _task() -> None:
        await _execute_run(app_state, run.run_id, authorization)

    task = asyncio.create_task(_task())
    app_state._tasks.add(task)
    task.add_done_callback(app_state._tasks.discard)

    _stamp_action_log(
        request,
        agent=agent_name,
        workflow=run.workflow,
        run_id=run.run_id,
        spiffe_id=run.spiffe_id,
        user_space=run.user_space,
        goal=run.goal,
        run_status=run.status,
    )
    return {
        "run_id": run.run_id,
        "status": run.status,
        "workflow": run.workflow,
        "user_space": run.user_space,
        "spiffe_id": run.spiffe_id,
        "correlation_id": run.correlation_id,
    }


@app.get("/agent/runs/{run_id}")
async def get_run(run_id: str, request: Request) -> dict[str, Any]:
    """Fetch run manifest, steps, handoffs, and blackboard entries.

    Example:
        >>> import inspect
        >>> from thot.tools.agent.app import get_run
        >>> inspect.iscoroutinefunction(get_run)
        True
    """
    app_state: AppState = request.app.state.agent
    state = app_state.store.read_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run not found")
    _stamp_action_log(
        request,
        agent=state.agent,
        workflow=state.workflow,
        run_id=state.run_id,
        spiffe_id=state.spiffe_id,
        user_space=state.user_space,
        goal=state.goal,
        run_status=state.status,
    )
    steps = app_state.store.list_steps(run_id)
    blackboard: list[Any] = []
    bb_path = app_state.store.blackboard_path(run_id)
    if bb_path.is_file():
        import json

        blackboard = (
            json.loads(bb_path.read_text(encoding="utf-8")).get("entries")
            or []
        )
    return {
        "run": state.model_dump(by_alias=True, mode="json"),
        "steps": [s.model_dump(mode="json") for s in steps],
        "handoffs": [h.model_dump(mode="json") for h in state.handoffs],
        "blackboard": blackboard,
        "compose_result": state.compose_result,
        "budgets": {
            "limits": state.budgets.model_dump(),
            "usage": state.usage.model_dump(),
        },
    }


@app.post("/agent/runs/{run_id}/cancel")
async def cancel_run(run_id: str, request: Request) -> dict[str, Any]:
    """Request cancellation of a queued or running agent run.

    Example:
        >>> import inspect
        >>> from thot.tools.agent.app import cancel_run
        >>> inspect.iscoroutinefunction(cancel_run)
        True
    """
    app_state: AppState = request.app.state.agent
    state = app_state.store.request_cancel(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run not found")
    _stamp_action_log(
        request,
        agent=state.agent,
        workflow=state.workflow,
        run_id=state.run_id,
        spiffe_id=state.spiffe_id,
        user_space=state.user_space,
        goal=state.goal,
        run_status=state.status,
    )
    return {"run_id": run_id, "status": state.status, "cancel_requested": True}


class PublishBody(BaseModel):
    approval_id: str | None = None


@app.post("/agent/runs/{run_id}/publish")
async def publish_agent_run(
    run_id: str,
    request: Request,
    body: PublishBody | None = None,
) -> dict[str, Any]:
    """Approval-gated publication of an agent deliverable.

    Example:
        >>> import inspect
        >>> from thot.tools.agent.app import publish_agent_run
        >>> inspect.iscoroutinefunction(publish_agent_run)
        True
    """
    app_state: AppState = request.app.state.agent
    state = app_state.store.read_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run not found")
    _stamp_action_log(
        request,
        agent=state.agent,
        workflow=state.workflow,
        run_id=state.run_id,
        spiffe_id=state.spiffe_id,
        user_space=state.user_space,
        goal=state.goal,
        run_status=state.status,
    )
    payload = body or PublishBody()
    result = publish_run(
        store=app_state.store,
        guard_approvals=app_state.guard.approvals,
        state=state,
        approval_id=payload.approval_id,
        mode=app_state.guard.mode,
    )
    if result.get("status") == "rejected":
        raise HTTPException(status_code=400, detail=result.get("error"))
    app_state.guard.emit(
        kind="agent.publish",
        state=state,
        intent="generate",
        status="success" if result.get("status") == "published" else "pending",
        ext=result,
    )
    return result


def main(argv: list[str] | None = None) -> None:
    """Run the agent HTTP service with uvicorn.

    Args:
        argv: Optional CLI arguments (host/port/config overrides).

    Example:
        >>> import inspect
        >>> from thot.tools.agent.app import main
        >>> callable(main)
        True
    """
    parser = argparse.ArgumentParser(
        description=(
            "T-KEIR agent HTTP service (tool). "
            "Hosts a set of library agents from YAML configuration dirs."
        )
    )
    parser.add_argument("--host", default=os.getenv("AGENT_HOST", "0.0.0.0"))
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("AGENT_PORT", "8092"))
    )
    parser.add_argument(
        "--config-dir",
        action="append",
        default=[],
        metavar="DIR",
        help=(
            "Agent YAML directory (repeatable). Appended to the default "
            "search path / TKEIR_AGENT_CONFIG_DIRS."
        ),
    )
    parser.add_argument(
        "--agents",
        default=os.getenv("TKEIR_AGENT_NAMES", ""),
        help=(
            "Comma-separated agent name allow-list. Empty = all agents found "
            "in the configuration directories."
        ),
    )
    args = parser.parse_args(argv)
    names = [n.strip() for n in str(args.agents or "").split(",") if n.strip()]
    configure_agents(
        config_dirs=list(args.config_dir) or None,
        names=names or None,
    )
    import uvicorn

    uvicorn.run(
        "thot.tools.agent.app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
