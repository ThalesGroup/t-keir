"""Title: Multi-agent orchestrator from scratch (Phase D) — sequential only.

Supervisor plan comes from ``WorkflowSpec`` YAML. Each agent phase runs the
existing :class:`AgentLoop`; compose phases use ``thot.compose``. Builtin
steps (e.g. OKF scoped export) run in-process helpers. Explicit
:class:`Handoff` records and an append-only blackboard carry decision context
between agents (memory / delegation). Index provenance lives on findings and
tool observations when those tools are used — not on the handoff contract.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from thot.action.models import utc_now_rfc3339
from thot.action.sink import default_action_sink
from thot.agent.guard import AgentGuard
from thot.agent.loop import AgentLoop, LlmClient
from thot.agent.models import (
    AgentSpec,
    Handoff,
    RunState,
    StopCondition,
    WorkflowSpec,
    WorkflowStep,
)
from thot.agent.registry import load_agent_spec
from thot.agent.runs import RunStore
from thot.agent.toolbox import ToolRegistry
from thot.compose.composer import compose
from thot.compose.findings_kg import (
    findings_prose_context,
    ontology_payloads_from_observations,
    turtles_from_grounded_findings,
)
from thot.compose.kg import UserSpaceKG
from thot.compose.writers import DeterministicWriter, FindingsGroundedWriter
from thot.core.ThotMetrics import ThotMetrics
from thot.mcp.client import OutboundMcpClient, default_outbound_client
from thot.mcp.handlers import McpHandlers
from thot.okf.applicator import (
    OkfEnrichmentApplicator,
    enrichments_from_grounded,
)
from thot.okf.exporter import default_okf_root, export_scoped, user_okf_root
from thot.okf.models import OkfExportRequest

LOGGER = logging.getLogger(__name__)

# Full wiki for INTSUM / persona report goals (Sources + Evidence must survive).
_WIKI_EXCERPT_MAX = 100_000


def _format_exc(exc: BaseException) -> str:
    """Human-readable exception text (httpx timeouts often have empty str()).

    Args:
        exc: Exception to stringify.

    Returns:
        ``TypeName: message`` or type-only when ``str(exc)`` is empty.

    Example:
        >>> from thot.agent.orchestrator import _format_exc
        >>> _format_exc(ValueError("bad"))
        'ValueError: bad'
        >>> _format_exc(TimeoutError())
        'TimeoutError'
    """
    msg = str(exc).strip()
    if msg:
        return f"{type(exc).__name__}: {msg}"
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        cause_msg = str(cause).strip()
        if cause_msg:
            return f"{type(exc).__name__}: {cause_msg}"
        return f"{type(exc).__name__} ({type(cause).__name__})"
    return type(exc).__name__


def _orchestrator_cfg(params: dict[str, Any] | None = None):
    """Resolve usecase orchestrator config (OSINT / enterprise / …).

    Args:
        params: Run params; ``usecase`` / ``dataset`` selects the pack.

    Returns:
        :class:`~thot.agent.orchestrator_config.OrchestratorConfig` for the pack.

    Example:
        >>> from thot.agent.orchestrator import _orchestrator_cfg
        >>> _orchestrator_cfg({"usecase": "osint"}).default_report_form
        'intsum'
    """
    from thot.agent.orchestrator_config import get_orchestrator_config

    params = params or {}
    usecase = str(
        params.get("usecase")
        or params.get("dataset")
        or params.get("business_ontology_dataset")
        or ""
    ).strip()
    return get_orchestrator_config(usecase)


def _truthy(value: Any) -> bool:
    """Return whether a workflow param value is truthy.

    Args:
        value: Raw param (string, number, or ``None``).

    Returns:
        ``True`` when normalized value is ``1``, ``true``, ``yes``, or ``on``.

    Example:
        >>> from thot.agent.orchestrator import _truthy
        >>> _truthy("yes")
        True
        >>> _truthy("0")
        False
    """
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _format_goal(template: str, *, goal: str, params: dict[str, Any]) -> str:
    """Substitute ``{placeholders}`` without interpreting braces inside values.

    Args:
        template: Goal template with ``{key}`` placeholders.
        goal: Primary run goal (always available as ``{goal}``).
        params: Extra substitution context.

    Returns:
        Formatted goal string.

    Example:
        >>> from thot.agent.orchestrator import _format_goal
        >>> _format_goal("Research {topic}", goal="g", params={"topic": "AI"})
        'Research AI'
    """
    ctx: dict[str, Any] = {"goal": goal, **params}
    out = template
    for key in sorted(ctx.keys(), key=len, reverse=True):
        placeholder = "{" + str(key) + "}"
        if placeholder not in out:
            continue
        raw = ctx[key]
        out = out.replace(placeholder, "" if raw is None else str(raw))
    return out


def _load_wiki_markdown(user_space: str, bundle_id: str) -> str:
    """Load ``wiki.md`` from OKF for ``bundle_id``; empty when id is missing.

    Args:
        user_space: Tenant streaming group.
        bundle_id: OKF bundle identifier.

    Returns:
        Wiki markdown text, or ``""`` when unavailable.

    Example:
        >>> from thot.agent.orchestrator import _load_wiki_markdown
        >>> _load_wiki_markdown("dev@tkeir", "")
        ''
    """
    bid = (bundle_id or "").strip()
    if not bid:
        return ""
    try:
        from thot.okf.store import OkfBundleStore

        text = OkfBundleStore().get_wiki(bid, user_space)
    except Exception:  # noqa: BLE001
        LOGGER.debug("wiki seed: okf get_wiki failed", exc_info=True)
        return ""
    return (text or "").strip()


def _seed_wiki_params(state: RunState) -> None:
    """Attach LLM Wiki markdown for Reporter / persona report workflows.

    Prefer explicit ``wiki_markdown`` from the HMI (edited Phase-2 wiki).
    Else, when ``use_existing_wiki`` is set, load ``wiki.md`` from ``bundle_id``.

    Args:
        state: Run state whose ``params`` are updated in place.

    Example:
        >>> from thot.agent.models import RunState
        >>> from thot.agent.orchestrator import _seed_wiki_params
        >>> state = RunState(goal="g", params={"wiki_markdown": "# Wiki"})
        >>> _seed_wiki_params(state)
        >>> state.params["has_llm_wiki"]
        'true'
    """
    params = dict(state.params or {})
    wiki = str(params.get("wiki_markdown") or "").strip()
    if not wiki and _truthy(params.get("use_existing_wiki")):
        wiki = _load_wiki_markdown(
            state.user_space, str(params.get("bundle_id") or "")
        )
    params["wiki_markdown"] = wiki
    # Persona goals use full wiki (Answer + Evidence + Sources) for INTSUM.
    if wiki and len(wiki) > _WIKI_EXCERPT_MAX:
        params["wiki_excerpt"] = (
            wiki[:_WIKI_EXCERPT_MAX] + "\n\n…[wiki truncated for goal]"
        )
    else:
        params["wiki_excerpt"] = wiki
    # Keep markdown + excerpt aligned for templates that still mention excerpt.
    if wiki:
        params["wiki_markdown"] = wiki
    params["has_llm_wiki"] = "true" if wiki else "false"
    cfg = _orchestrator_cfg(params)
    form = (
        str(params.get("report_form") or cfg.default_report_form)
        .strip()
        .lower()
    )
    params.setdefault("report_form", form)
    params.setdefault("report_form_slots", cfg.slot_hint_for(form))
    state.params = params


def _prior_findings_json(state: RunState) -> str:
    """Serialize prior grounded findings for goal templates.

    Args:
        state: Run state with optional ``result`` findings.

    Returns:
        JSON array string, or ``"[]"`` when empty or on serialization error.

    Example:
        >>> from thot.agent.models import GroundedFinding, GroundedFindings, RunState
        >>> from thot.agent.orchestrator import _prior_findings_json
        >>> state = RunState(goal="g")
        >>> _prior_findings_json(state)
        '[]'
        >>> state.result = GroundedFindings(findings=[GroundedFinding(claim="x")])
        >>> '"claim": "x"' in _prior_findings_json(state)
        True
    """
    if state.result is None:
        return "[]"
    try:
        return json.dumps(
            [f.model_dump(mode="json") for f in state.result.findings],
            ensure_ascii=False,
        )
    except Exception:  # noqa: BLE001
        return "[]"


def _compose_payloads_for_state(
    state: RunState,
    store: RunStore,
) -> tuple[list[str], list[str], str, list[str], list[str]]:
    """Build KG turtles + findings prose from the run (never demo fixtures).

    Args:
        state: Run state with optional findings and params.
        store: Run store for step observations.

    Returns:
        Tuple of turtles, document ids, findings prose, chunk ids, doc ids.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.agent.models import GroundedFinding, GroundedFindings, RunState
        >>> from thot.agent.orchestrator import _compose_payloads_for_state
        >>> from thot.agent.runs import RunStore
        >>> with tempfile.TemporaryDirectory() as td:
        ...     store = RunStore(Path(td))
        ...     state = RunState(
        ...         goal="summarize",
        ...         result=GroundedFindings(
        ...             findings=[GroundedFinding(claim="fact", chunk_ids=["c1"])]
        ...         ),
        ...     )
        ...     _, _, _, chunks, _ = _compose_payloads_for_state(state, store)
        ...     "c1" in chunks
        True
    """
    turtles: list[str] = []
    document_ids: list[str] = []

    findings_turtle, finding_docs = turtles_from_grounded_findings(
        state.result,
        goal=state.goal,
    )
    turtles.extend(findings_turtle)
    document_ids.extend(finding_docs)

    observations: list[dict[str, Any]] = []
    try:
        for step in store.list_steps(state.run_id):
            if isinstance(step.observation, dict):
                observations.append(step.observation)
    except Exception:  # noqa: BLE001
        LOGGER.debug(
            "compose: unable to read steps for ontology payloads",
            exc_info=True,
        )
    turtles.extend(ontology_payloads_from_observations(observations))

    # Optional explicit ontology / turtle payloads on run params.
    params = state.params or {}
    for key in ("ontology_json_ld", "compose_json_ld", "compose_turtle"):
        raw = params.get(key)
        if isinstance(raw, str) and raw.strip():
            turtles.append(raw.strip())
        elif isinstance(raw, list):
            turtles.extend(str(item) for item in raw if str(item).strip())

    prose, chunks, docs = findings_prose_context(state.result)
    document_ids = sorted(set(document_ids + docs))
    return turtles, document_ids, prose, chunks, docs


def _sync_params_after_agent(state: RunState) -> None:
    """Expose findings + defaults so later goal_templates can format them.

    Args:
        state: Run state whose ``params`` are updated in place.

    Example:
        >>> from thot.agent.models import RunState
        >>> from thot.agent.orchestrator import _sync_params_after_agent
        >>> state = RunState(goal="g")
        >>> _sync_params_after_agent(state)
        >>> "prior_findings_json" in state.params
        True
    """
    params = dict(state.params or {})
    cfg = _orchestrator_cfg(params)
    params.setdefault("report_form", cfg.default_report_form)
    params.setdefault("use_existing_wiki", "false")
    params.setdefault("bundle_id", params.get("bundle_id") or "")
    params.setdefault("wiki_markdown", params.get("wiki_markdown") or "")
    params.setdefault("wiki_excerpt", params.get("wiki_excerpt") or "")
    params.setdefault("has_llm_wiki", params.get("has_llm_wiki") or "false")
    params.setdefault(
        "report_form_slots",
        params.get("report_form_slots")
        or cfg.slot_hint_for(params.get("report_form")),
    )
    params["prior_findings_json"] = _prior_findings_json(state)
    state.params = params


class Orchestrator:
    """Sequential supervisor/worker runner.

    Example:
        >>> from thot.agent.orchestrator import Orchestrator
        >>> Orchestrator  # doctest: +ELLIPSIS
        <class 'thot.agent.orchestrator.Orchestrator'>
    """

    def __init__(
        self,
        *,
        store: RunStore,
        guard: AgentGuard,
        llm: LlmClient,
        outbound: OutboundMcpClient | None = None,
        handlers: McpHandlers | None = None,
    ) -> None:
        """Wire run store, guard, LLM, and optional MCP handlers.

        Args:
            store: Filesystem run store.
            guard: Agent safety / audit guard.
            llm: LLM client for agent and wiki steps.
            outbound: Optional outbound MCP client (defaults when omitted).
            handlers: Optional in-process MCP tool handlers.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.orchestrator import Orchestrator
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     root = Path(td)
            ...     orch = Orchestrator(
            ...         store=RunStore(root),
            ...         guard=AgentGuard(root / "gov"),
            ...         llm=object(),
            ...     )
            ...     orch.handlers is None
            True
        """
        self.store = store
        self.guard = guard
        self.llm = llm
        self.outbound = outbound or default_outbound_client()
        self.handlers = handlers

    def _wiki_workflow(self) -> Any:
        """Lazy :class:`~thot.agent.workflows.wiki_generator.WikiGeneratorWorkflow`.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.orchestrator import Orchestrator
            >>> from thot.agent.runs import RunStore
            >>> from thot.agent.workflows.wiki_generator import (
            ...     WikiGeneratorWorkflow,
            ... )
            >>> with tempfile.TemporaryDirectory() as td:
            ...     root = Path(td)
            ...     orch = Orchestrator(
            ...         store=RunStore(root),
            ...         guard=AgentGuard(root / "gov"),
            ...         llm=object(),
            ...     )
            ...     isinstance(orch._wiki_workflow(), WikiGeneratorWorkflow)
            True
        """
        from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow

        return WikiGeneratorWorkflow(
            store=self.store, guard=self.guard, llm=self.llm
        )

    async def run(
        self,
        state: RunState,
        workflow: WorkflowSpec,
        *,
        authorization: str | None = None,
    ) -> RunState:
        """Execute workflow steps sequentially until compose or failure.

        Example:
            >>> import inspect
            >>> from thot.agent.orchestrator import Orchestrator
            >>> inspect.iscoroutinefunction(Orchestrator.run)
            True
        """
        ThotMetrics.create_counter(
            short_name="workflow_runs",
            function_name="workflow_runs_total",
            counter_description="Multi-agent workflow runs",
        )
        ThotMetrics.increment_counter(
            short_name="workflow_runs",
            method="WORKFLOW",
            path=f"/workflow/{workflow.name}",
            status=200,
        )

        state.workflow = workflow.name
        state.budgets = workflow.budgets
        state.status = "running"
        state.started_at = state.started_at or utc_now_rfc3339()
        state.delegation_chain = ["supervisor", workflow.name]
        params = dict(state.params or {})
        cfg = _orchestrator_cfg(params)
        params.setdefault("report_form", cfg.default_report_form)
        params.setdefault("use_existing_wiki", "false")
        params.setdefault("topic", params.get("topic") or state.goal)
        params.setdefault("prior_findings_json", "[]")
        params.setdefault("bundle_id", "")
        state.params = params
        _seed_wiki_params(state)
        self.guard.mint_run_token(
            actor_id=state.user_space, run_id=state.run_id
        )
        self.guard.emit(
            kind="agent.plan",
            state=state,
            intent="agent.run",
            ext={"workflow": workflow.name},
        )
        self.store.write_state(state)

        step_offset = 0
        previous_agent = "supervisor"

        for wf_step in workflow.steps:
            if self.guard.is_agents_killed() or state.cancel_requested:
                state.status = "killed"
                state.error = "killed during workflow"
                state.ended_at = utc_now_rfc3339()
                self.store.write_state(state)
                return state

            if wf_step.compose is not None:
                state = self._run_compose(state, workflow, wf_step)
                return state

            if wf_step.builtin:
                state = await self._run_builtin_step(
                    state,
                    workflow,
                    wf_step,
                    previous_agent=previous_agent,
                )
                if state.status in {
                    "failed",
                    "blocked",
                    "killed",
                    "cancelled",
                }:
                    return state
                previous_agent = f"builtin:{wf_step.builtin}"
                continue

            if not wf_step.agent:
                state.status = "failed"
                state.error = f"workflow step {wf_step.id!r} missing agent"
                state.ended_at = utc_now_rfc3339()
                self.store.write_state(state)
                return state

            state = await self._run_agent_step(
                state,
                workflow,
                wf_step,
                previous_agent=previous_agent,
                step_offset=step_offset,
                authorization=authorization,
            )
            if state.status in {"failed", "blocked", "killed", "cancelled"}:
                return state

            if wf_step.agent == "okf_curator":
                self._apply_okf_enrichments(state)

            _sync_params_after_agent(state)
            step_offset = state.steps_completed
            previous_agent = wf_step.agent

        state.status = "succeeded"
        state.ended_at = utc_now_rfc3339()
        self.store.write_state(state)
        return state

    async def _run_builtin_step(
        self,
        state: RunState,
        workflow: WorkflowSpec,
        wf_step: WorkflowStep,
        *,
        previous_agent: str,
    ) -> RunState:
        """Execute one builtin workflow step (OKF export / iterative wiki).

        Example:
            >>> import inspect
            >>> from thot.agent.orchestrator import Orchestrator
            >>> inspect.iscoroutinefunction(Orchestrator._run_builtin_step)
            True
        """
        assert wf_step.builtin is not None
        handoff = Handoff(
            from_agent=previous_agent,
            to_agent=f"builtin:{wf_step.builtin}",
            reason=f"workflow:{workflow.name}:{wf_step.id}",
            payload_summary=wf_step.builtin,
        )
        state.handoffs.append(handoff)
        state.delegation_chain = list(
            dict.fromkeys(
                [*state.delegation_chain, f"builtin:{wf_step.builtin}"]
            )
        )
        self.store.append_blackboard(
            state.run_id,
            {
                "kind": "handoff",
                "from": handoff.from_agent,
                "to": handoff.to_agent,
                "reason": handoff.reason,
                "provenance": "orchestrator",
                "builtin": wf_step.builtin,
            },
        )
        self.guard.emit(
            kind="agent.handoff",
            state=state,
            intent="agent.run",
            ext={
                "from_agent": handoff.from_agent,
                "to_agent": handoff.to_agent,
                "handoff_id": handoff.handoff_id,
                "builtin": wf_step.builtin,
            },
        )

        if wf_step.builtin == "okf_scoped_export":
            state = await self._run_okf_scoped_export(state, wf_step)
        elif wf_step.builtin == "okf_iterative_wiki":
            # Legacy path — default to wiki_upsert unless wiki_mode=iterative.
            mode = (
                str((state.params or {}).get("wiki_mode") or "")
                .strip()
                .lower()
            )
            wiki_wf = self._wiki_workflow()
            if mode == "iterative":
                state = await wiki_wf.run_iterative(state)
            else:
                state = await wiki_wf.run_upsert(state)
        elif wf_step.builtin == "wiki_upsert":
            state = await self._wiki_workflow().run_upsert(state)
        elif wf_step.builtin == "answer_generate":
            state = await self._run_answer_generate(state, wf_step)
        elif wf_step.builtin == "search_chunks":
            state = await self._run_search_chunks(state, wf_step)
        else:
            state.status = "failed"
            state.error = f"unknown builtin step: {wf_step.builtin!r}"
            state.ended_at = utc_now_rfc3339()
            self.store.write_state(state)
        return state

    def _bundle_root(self, state: RunState, bundle_id: str) -> Path | None:
        """Resolve OKF bundle directory for ``bundle_id``.

        Args:
            state: Run state (provides ``user_space``).
            bundle_id: OKF bundle identifier.

        Returns:
            Existing bundle directory, or ``None`` when not found.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.models import RunState
            >>> from thot.agent.orchestrator import Orchestrator
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     root = Path(td)
            ...     orch = Orchestrator(
            ...         store=RunStore(root),
            ...         guard=AgentGuard(root / "gov"),
            ...         llm=object(),
            ...     )
            ...     orch._bundle_root(
            ...         RunState(goal="g", user_space="dev@tkeir"), "missing"
            ...     ) is None
            True
        """
        bid = (bundle_id or "").strip()
        if not bid:
            return None
        root = user_okf_root(state.user_space) / bid
        if root.is_dir():
            return root
        legacy = default_okf_root() / bid
        if legacy.is_dir():
            return legacy
        return None

    def _fail_builtin(self, state: RunState, *, error: str) -> RunState:
        """Mark a builtin step failed and persist.

        Args:
            state: Run state to update.
            error: Failure message stored on ``state.error``.

        Returns:
            Updated run state with ``status`` ``failed``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.models import RunState
            >>> from thot.agent.orchestrator import Orchestrator
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     root = Path(td)
            ...     store = RunStore(root)
            ...     orch = Orchestrator(
            ...         store=store,
            ...         guard=AgentGuard(root / "gov"),
            ...         llm=object(),
            ...     )
            ...     out = orch._fail_builtin(
            ...         RunState(goal="g"), error="boom"
            ...     )
            ...     out.status
            'failed'
        """
        state.status = "failed"
        state.error = error
        state.ended_at = utc_now_rfc3339()
        self.store.write_state(state)
        return state

    @staticmethod
    def _wiki_chunks_for_bundle(
        params: dict[str, Any], root: Path
    ) -> list[dict[str, str]]:
        """Prefer HMI grab/search chunks; else load bundle evidence_chunks.json.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.orchestrator import Orchestrator
            >>> with tempfile.TemporaryDirectory() as td:
            ...     Orchestrator._wiki_chunks_for_bundle({}, Path(td))
            []
        """
        from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow

        return WikiGeneratorWorkflow.wiki_chunks_for_bundle(params, root)

    @staticmethod
    def _seed_or_load_wiki(
        *,
        bundle_id: str,
        user_space: str,
        query: str,
        wiki_cfg: dict[str, Any],
        store: Any,
    ) -> str:
        """Return existing wiki or a persona/OKF seed skeleton.

        Example:
            >>> class _Store:
            ...     def get_wiki(self, *_a, **_k):
            ...         return "# Existing\\nbody"
            >>> from thot.agent.orchestrator import Orchestrator
            >>> Orchestrator._seed_or_load_wiki(
            ...     bundle_id="b",
            ...     user_space="u",
            ...     query="q",
            ...     wiki_cfg={"structured_facts_seed": ""},
            ...     store=_Store(),
            ... ).startswith("# Existing")
            True
        """
        from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow

        return WikiGeneratorWorkflow.seed_or_load_wiki(
            bundle_id=bundle_id,
            user_space=user_space,
            query=query,
            wiki_cfg=wiki_cfg,
            store=store,
        )

    @staticmethod
    def _findings_from_wiki_chunks(
        chunks: list[dict[str, str]],
        *,
        max_chunks: int,
        query: str,
        path: Any,
        prompt_name: str,
    ) -> Any:
        """Build grounded findings stubs from wiki evidence chunks.

        Example:
            >>> from thot.agent.orchestrator import Orchestrator
            >>> out = Orchestrator._findings_from_wiki_chunks(
            ...     [{"chunk_id": "c1", "text_raw": "fact", "parent_doc_id": "d1"}],
            ...     max_chunks=2,
            ...     query="q",
            ...     path="/tmp/w",
            ...     prompt_name="p",
            ... )
            >>> out.findings[0].claim
            'fact'
        """
        from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow

        return WikiGeneratorWorkflow.findings_from_wiki_chunks(
            chunks,
            max_chunks=max_chunks,
            query=query,
            path=path,
            prompt_name=prompt_name,
        )

    async def _run_search_chunks(
        self, state: RunState, wf_step: WorkflowStep
    ) -> RunState:
        """Retrieve chunks via RAG ``POST /search`` (no answer generation).

        Prefers ``params.chunks`` / ``params.grab_chunks`` when already set
        (HMI Grab path). Otherwise calls the RAG search HTTP API.

        Example:
            >>> import inspect
            >>> from thot.agent.orchestrator import Orchestrator
            >>> inspect.iscoroutinefunction(Orchestrator._run_search_chunks)
            True
        """
        import httpx

        _ = wf_step
        params = dict(state.params or {})
        query = str(
            params.get("query") or params.get("topic") or state.goal or ""
        ).strip()
        if not query:
            return self._fail_builtin(
                state, error="search_chunks: missing query"
            )
        existing = params.get("chunks") or params.get("grab_chunks")
        if isinstance(existing, list) and existing:
            state.params = {**params, "chunks": existing}
            self.store.append_blackboard(
                state.run_id,
                {
                    "kind": "builtin",
                    "builtin": "search_chunks",
                    "source": "params.chunks",
                    "chunk_count": len(existing),
                    "provenance": "orchestrator",
                },
            )
            self.store.write_state(state)
            return state

        rag_url = os.getenv("RAG_URL", "http://127.0.0.1:8090").rstrip("/")
        try:
            hits = max(1, min(int(params.get("hits") or 20), 100))
        except (TypeError, ValueError):
            hits = 20
        body: dict[str, Any] = {
            "query": query,
            "language": str(params.get("language") or "en"),
            "hits": hits,
            "search_mode": str(params.get("search_mode") or "both"),
        }
        headers: dict[str, str] = {"Content-Type": "application/json"}
        auth = str(params.get("authorization") or "").strip()
        if auth:
            headers["Authorization"] = auth
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{rag_url}/search", headers=headers, json=body
                )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("search_chunks failed")
            return self._fail_builtin(
                state, error=f"search_chunks: {_format_exc(exc)}"
            )
        chunks = payload.get("chunks") or payload.get("hits") or []
        if not isinstance(chunks, list):
            chunks = []
        state.params = {**params, "chunks": chunks, "query": query}
        self.store.append_blackboard(
            state.run_id,
            {
                "kind": "builtin",
                "builtin": "search_chunks",
                "source": "rag_search",
                "chunk_count": len(chunks),
                "provenance": "orchestrator",
            },
        )
        self.store.write_state(state)
        return state

    async def _run_wiki_upsert(
        self, state: RunState, wf_step: WorkflowStep
    ) -> RunState:
        """Delegate to :class:`~thot.agent.workflows.wiki_generator.WikiGeneratorWorkflow`.

        Example:
            >>> import inspect
            >>> from thot.agent.orchestrator import Orchestrator
            >>> inspect.iscoroutinefunction(Orchestrator._run_wiki_upsert)
            True
        """
        _ = wf_step
        return await self._wiki_workflow().run_upsert(state)

    def _answer_stop_at_wiki(
        self, state: RunState, params: dict[str, Any]
    ) -> RunState | None:
        """Handle ``stop_at_wiki_extract`` short-circuit; else return ``None``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.models import RunState
            >>> from thot.agent.orchestrator import Orchestrator
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     root = Path(td)
            ...     orch = Orchestrator(
            ...         store=RunStore(root),
            ...         guard=AgentGuard(root / "gov"),
            ...         llm=object(),
            ...     )
            ...     orch._answer_stop_at_wiki(RunState(goal="g"), {}) is None
            True
        """
        if not _truthy(params.get("stop_at_wiki_extract")):
            return None
        wiki = str(
            params.get("wiki_extract")
            or params.get("wiki_excerpt")
            or params.get("wiki_markdown")
            or ""
        ).strip()
        state.params = {
            **params,
            "answer_markdown": "",
            "stopped_at": "wiki_extract",
            "wiki_extract": wiki,
        }
        self.store.append_blackboard(
            state.run_id,
            {
                "kind": "builtin",
                "builtin": "answer_generate",
                "skipped": True,
                "reason": "stop_at_wiki_extract",
                "wiki_chars": len(wiki),
                "provenance": "orchestrator",
            },
        )
        self.store.write_state(state)
        return state

    @staticmethod
    def _answer_resolve_template(params: dict[str, Any]) -> str:
        """Map run params to a compose template name.

        Example:
            >>> from thot.agent.orchestrator import Orchestrator
            >>> Orchestrator._answer_resolve_template(
            ...     {"answer_template": "synthesis_note"}
            ... )
            'synthesis_note'
        """
        from thot.agent.orchestrator_config import load_orchestrator_config

        raw_template = str(
            params.get("answer_template")
            or params.get("template")
            or params.get("report_form")
            or ""
        ).strip()
        usecase = str(
            params.get("usecase") or params.get("dataset") or ""
        ).strip()
        cfg = load_orchestrator_config(usecase=usecase or None)
        mapped = cfg.template_for(raw_template) if raw_template else None
        return (
            mapped
            or raw_template
            or cfg.template_for(cfg.default_report_form)
            or "synthesis_note"
        )

    @staticmethod
    def _answer_findings_from_sources(
        *, wiki: str, chunks_raw: list[Any]
    ) -> tuple[str, list[str], list[str]]:
        """Build findings prose + id lists from wiki extract and grab chunks.

        Example:
            >>> from thot.agent.orchestrator import Orchestrator
            >>> prose, cids, _ = Orchestrator._answer_findings_from_sources(
            ...     wiki="",
            ...     chunks_raw=[{"chunk_id": "c1", "text_raw": "hello world"}],
            ... )
            >>> "c1" in cids and "hello" in prose
            True
        """
        findings_lines: list[str] = []
        chunk_ids: list[str] = []
        doc_ids: list[str] = []
        if wiki:
            findings_lines.append(
                f"- [executive_summary] Wiki prior:\n{wiki[:1200]}"
            )
            findings_lines.append(f"- [situation] Wiki prior:\n{wiki[:1200]}")
        for raw in chunks_raw[:12]:
            if not isinstance(raw, dict):
                continue
            cid = str(raw.get("chunk_id") or "").strip()
            text = str(
                raw.get("text_raw")
                or raw.get("text")
                or raw.get("content")
                or ""
            ).strip()
            parent = str(
                raw.get("parent_doc_id") or raw.get("document_id") or ""
            ).strip()
            if not text:
                continue
            if cid:
                chunk_ids.append(cid)
            if parent:
                doc_ids.append(parent)
            clip = text[:600]
            findings_lines.append(f"- [situation] {clip} (chunk_id={cid})")
            findings_lines.append(
                f"- [executive_summary] {clip} (chunk_id={cid})"
            )
        return "\n".join(findings_lines), chunk_ids, doc_ids

    async def _run_answer_generate(
        self, state: RunState, wf_step: WorkflowStep
    ) -> RunState:
        """Fill a compose template from chunks (+ optional wiki extract).

        Example:
            >>> import inspect
            >>> from thot.agent.orchestrator import Orchestrator
            >>> inspect.iscoroutinefunction(Orchestrator._run_answer_generate)
            True
        """
        from thot.compose.composer import compose
        from thot.compose.kg import UserSpaceKG
        from thot.compose.writers import FindingsGroundedWriter
        from thot.okf.wiki_match import extract_wiki_sections

        _ = wf_step
        params = dict(state.params or {})
        stopped = self._answer_stop_at_wiki(state, params)
        if stopped is not None:
            return stopped

        query = str(
            params.get("query") or params.get("topic") or state.goal or ""
        ).strip()
        template = self._answer_resolve_template(params)
        chunks_raw = params.get("chunks") or params.get("grab_chunks") or []
        if not isinstance(chunks_raw, list):
            chunks_raw = []

        wiki = str(
            params.get("wiki_extract")
            or params.get("wiki_excerpt")
            or params.get("wiki_markdown")
            or ""
        ).strip()
        if wiki:
            wiki = extract_wiki_sections(wiki, max_chars=2400)

        findings_prose, chunk_ids, doc_ids = (
            self._answer_findings_from_sources(
                wiki=wiki, chunks_raw=chunks_raw
            )
        )
        if not findings_prose.strip():
            return self._fail_builtin(
                state, error="answer_generate: no chunks or wiki extract"
            )

        writer = FindingsGroundedWriter(
            findings_context=findings_prose,
            chunk_ids=chunk_ids,
            document_ids=doc_ids,
        )
        kg = UserSpaceKG(state.user_space, use_process_cache=False)
        try:
            result = compose(
                template,
                kg=kg,
                topic=query or state.goal,
                params={**params, "wiki_excerpt": wiki, "query": query},
                writer=writer,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("answer_generate failed")
            return self._fail_builtin(
                state, error=f"answer_generate: {_format_exc(exc)}"
            )

        markdown = str(getattr(result, "markdown", "") or "")
        state.params = {
            **params,
            "answer_markdown": markdown,
            "answer_template": template,
            "wiki_extract": wiki,
        }
        state.compose_result = result.model_dump(by_alias=True, mode="json")
        state.agent = "answer_generate"
        self.store.append_blackboard(
            state.run_id,
            {
                "kind": "builtin",
                "builtin": "answer_generate",
                "template": template,
                "chunk_count": len(chunk_ids),
                "has_wiki": bool(wiki),
                "answer_chars": len(markdown),
                "provenance": "orchestrator",
            },
        )
        self.guard.emit(
            kind="agent.answer",
            state=state,
            intent="generate",
            ext={"template": template},
            chunk_ids=chunk_ids,
        )
        self.store.write_state(state)
        return state

    async def _run_okf_iterative_wiki(
        self, state: RunState, wf_step: WorkflowStep
    ) -> RunState:
        """Delegate legacy iterative wiki to :class:`WikiGeneratorWorkflow`.

        Example:
            >>> import inspect
            >>> from thot.agent.orchestrator import Orchestrator
            >>> inspect.iscoroutinefunction(Orchestrator._run_okf_iterative_wiki)
            True
        """
        _ = wf_step
        return await self._wiki_workflow().run_iterative(state)

    @staticmethod
    def _resolve_wiki_prompt_config(params: dict[str, Any]) -> dict[str, Any]:
        """Load persona ``*_prompt`` agent wiki seed/system from run params.

        Example:
            >>> from thot.agent.orchestrator import Orchestrator
            >>> cfg = Orchestrator._resolve_wiki_prompt_config({})
            >>> cfg["prompt_name"]
            ''
        """
        from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow

        return WikiGeneratorWorkflow.resolve_wiki_prompt_config(params)

    async def _run_okf_scoped_export(
        self, state: RunState, wf_step: WorkflowStep
    ) -> RunState:
        """Export or create an OKF evidence bundle (grab chunks or RAG scoped).

        Example:
            >>> import inspect
            >>> from thot.agent.orchestrator import Orchestrator
            >>> inspect.iscoroutinefunction(Orchestrator._run_okf_scoped_export)
            True
        """
        params = dict(state.params or {})
        for key in wf_step.params_from:
            if key not in params and key == "query":
                params["query"] = state.goal
            if key not in params and key == "topic":
                params["topic"] = params.get("topic") or state.goal
        query = str(params.get("query") or params.get("topic") or state.goal)

        # Reporter Grab already retrieved chunks — skip slow /rag/query export.
        from thot.okf.iterative_wiki import (
            chunks_from_params,
            create_evidence_bundle,
        )

        grab_chunks = chunks_from_params(params)
        out_key = wf_step.output_key or "bundle_id"
        if grab_chunks:
            wiki_cfg = self._resolve_wiki_prompt_config(params)
            try:
                bundle_id, root = create_evidence_bundle(
                    user_space=state.user_space,
                    query=query,
                    chunks=grab_chunks,
                    structured_facts_seed=wiki_cfg["structured_facts_seed"],
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("evidence-only OKF bundle failed")
                state.status = "failed"
                state.error = f"okf_scoped_export(evidence): {exc}"
                state.ended_at = utc_now_rfc3339()
                self.store.write_state(state)
                return state
            # Drop bulky chunk payloads from the run manifest (already on disk).
            slim = {
                k: v
                for k, v in params.items()
                if k not in {"chunks", "grab_chunks"}
            }
            state.params = {
                **slim,
                out_key: bundle_id,
                "evidence_only_bundle": True,
                "grab_chunk_count": len(grab_chunks),
                "prompt_name": wiki_cfg["prompt_name"],
                "wiki_agent": wiki_cfg["prompt_name"],
            }
            self.store.append_blackboard(
                state.run_id,
                {
                    "kind": "builtin",
                    "builtin": "okf_scoped_export",
                    "bundle_id": bundle_id,
                    "path": str(root),
                    "concept_count": 0,
                    "chunk_count": len(grab_chunks),
                    "mode": "evidence_chunks",
                    "provenance": "orchestrator",
                },
            )
            self.guard.emit(
                kind="okf.export.scoped",
                state=state,
                intent="okf.export",
                ext={
                    "bundle_id": bundle_id,
                    "path": str(root),
                    "mode": "evidence_chunks",
                },
            )
            self.store.write_state(state)
            return state

        request = OkfExportRequest(
            user_space=state.user_space,
            query=query,
            max_docs=int(params.get("max_docs") or 50),
            output_dir=None,
        )
        try:
            result = await export_scoped(
                request, action_sink=default_action_sink()
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("okf_scoped_export failed")
            state.status = "failed"
            state.error = f"okf_scoped_export: {exc}"
            state.ended_at = utc_now_rfc3339()
            self.store.write_state(state)
            return state
        state.params = {**params, out_key: result.bundle.bundle_id}
        self.store.append_blackboard(
            state.run_id,
            {
                "kind": "builtin",
                "builtin": "okf_scoped_export",
                "bundle_id": result.bundle.bundle_id,
                "path": result.bundle.path,
                "concept_count": result.bundle.concept_count,
                "mode": "rag_scoped",
                "provenance": "orchestrator",
            },
        )
        self.guard.emit(
            kind="okf.export.scoped",
            state=state,
            intent="okf.export",
            ext={
                "bundle_id": result.bundle.bundle_id,
                "path": result.bundle.path,
            },
        )
        self.store.write_state(state)
        return state

    def _apply_okf_enrichments(self, state: RunState) -> None:
        """Apply OKF curator enrichments to the bundle on disk when present.

        Args:
            state: Run state with ``bundle_id`` and grounded ``result``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.models import RunState
            >>> from thot.agent.orchestrator import Orchestrator
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     root = Path(td)
            ...     orch = Orchestrator(
            ...         store=RunStore(root),
            ...         guard=AgentGuard(root / "gov"),
            ...         llm=object(),
            ...     )
            ...     orch._apply_okf_enrichments(RunState(goal="g"))  # no-op
        """
        bundle_id = str((state.params or {}).get("bundle_id") or "")
        if not bundle_id or state.result is None:
            return
        root = user_okf_root(state.user_space) / bundle_id
        if not root.is_dir():
            # Legacy flat OKF_ROOT / blackboard absolute path
            legacy = default_okf_root() / bundle_id
            if legacy.is_dir():
                root = legacy
        if not root.is_dir():
            bb = self.store.blackboard_path(state.run_id)
            if bb.is_file():
                data = json.loads(bb.read_text(encoding="utf-8"))
                for entry in data.get("entries") or []:
                    if entry.get("bundle_id") == bundle_id and entry.get(
                        "path"
                    ):
                        root = Path(str(entry["path"]))
                        break
        if not root.is_dir():
            LOGGER.warning("okf applicator: bundle root missing %s", root)
            return
        enrichment = enrichments_from_grounded(state.result)
        summary = OkfEnrichmentApplicator(root).apply(enrichment)
        self.store.append_blackboard(
            state.run_id,
            {
                "kind": "okf_enrichment",
                "bundle_id": bundle_id,
                "summary": summary,
                "provenance": "orchestrator",
            },
        )

    async def _run_agent_step(
        self,
        state: RunState,
        workflow: WorkflowSpec,
        wf_step: WorkflowStep,
        *,
        previous_agent: str,
        step_offset: int,
        authorization: str | None,
    ) -> RunState:
        """Run one workflow agent phase via :class:`AgentLoop`.

        Example:
            >>> import inspect
            >>> from thot.agent.orchestrator import Orchestrator
            >>> inspect.iscoroutinefunction(Orchestrator._run_agent_step)
            True
        """
        assert wf_step.agent is not None
        spec = load_agent_spec(wf_step.agent)
        tools = list(
            wf_step.tools if wf_step.tools is not None else spec.tools
        )
        if wf_step.max_steps is not None:
            spec = AgentSpec(
                **{
                    **spec.model_dump(),
                    "tools": tools,
                    "stop": StopCondition(max_steps=wf_step.max_steps),
                    "budgets": workflow.budgets,
                }
            )
        else:
            spec = AgentSpec(
                **{
                    **spec.model_dump(),
                    "tools": tools,
                    "budgets": workflow.budgets,
                }
            )

        phase_goal = _format_goal(
            wf_step.goal_template, goal=state.goal, params=state.params
        )
        handoff = Handoff(
            from_agent=previous_agent,
            to_agent=wf_step.agent,
            reason=f"workflow:{workflow.name}:{wf_step.id}",
            payload_summary=phase_goal[:240],
        )
        state.handoffs.append(handoff)
        state.agent = wf_step.agent
        state.delegation_chain = list(
            dict.fromkeys([*state.delegation_chain, wf_step.agent])
        )
        self.store.append_blackboard(
            state.run_id,
            {
                "kind": "handoff",
                "from": handoff.from_agent,
                "to": handoff.to_agent,
                "reason": handoff.reason,
                "provenance": "orchestrator",
            },
        )
        self.guard.emit(
            kind="agent.handoff",
            state=state,
            intent="agent.run",
            ext={
                "from_agent": handoff.from_agent,
                "to_agent": handoff.to_agent,
                "handoff_id": handoff.handoff_id,
            },
        )
        self.store.write_state(state)

        toolbox = ToolRegistry(
            tools, handlers=self.handlers, outbound=self.outbound
        )
        loop = AgentLoop(
            store=self.store,
            guard=self.guard,
            llm=self.llm,
            toolbox=toolbox,
        )
        return await loop.run(
            state,
            spec,
            authorization=authorization,
            step_offset=step_offset,
            finalize=False,
            goal_override=phase_goal,
        )

    def _run_compose(
        self,
        state: RunState,
        workflow: WorkflowSpec,
        wf_step: WorkflowStep,
    ) -> RunState:
        """Run the final compose step and persist deliverable metadata.

        Args:
            state: Run state with findings and params.
            workflow: Parent workflow spec.
            wf_step: Compose workflow step configuration.

        Returns:
            Updated run state with ``compose_result`` and ``status`` succeeded.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.models import (
            ...     RunState,
            ...     WorkflowComposeStep,
            ...     WorkflowSpec,
            ...     WorkflowStep,
            ... )
            >>> from thot.agent.orchestrator import Orchestrator
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     root = Path(td)
            ...     store = RunStore(root)
            ...     guard = AgentGuard(root / "gov")
            ...     orch = Orchestrator(store=store, guard=guard, llm=object())
            ...     state = RunState(goal="topic", user_space="dev@tkeir")
            ...     wf = WorkflowSpec(name="wf", steps=[])
            ...     step = WorkflowStep(
            ...         id="compose", compose=WorkflowComposeStep()
            ...     )
            ...     out = orch._run_compose(state, wf, step)
            ...     out.status
            'succeeded'
        """
        compose_cfg = wf_step.compose
        assert compose_cfg is not None
        params = dict(state.params or {})
        cfg = _orchestrator_cfg(params)
        form = str(params.get("report_form") or params.get("template") or "")
        mapped = cfg.template_for(form)
        template = (
            mapped
            or compose_cfg.template
            or workflow.template
            or params.get("template")
            or "synthesis_note"
        )
        topic_key = compose_cfg.topic_from or "goal"
        topic = str(
            params.get(topic_key) or params.get("topic") or state.goal or ""
        ).strip()
        turtles, document_ids, findings_prose, finding_chunks, finding_docs = (
            _compose_payloads_for_state(state, self.store)
        )
        kg = UserSpaceKG(state.user_space, use_process_cache=False)
        if turtles:
            kg.load(turtles, document_ids=document_ids or None)
        else:
            LOGGER.warning(
                "compose run_id=%s has no findings/ontology payloads; "
                "slots will remain unfilled (demo KG disabled)",
                state.run_id,
            )
        writer: DeterministicWriter | FindingsGroundedWriter
        if findings_prose and finding_chunks:
            writer = FindingsGroundedWriter(
                findings_context=findings_prose,
                chunk_ids=finding_chunks,
                document_ids=finding_docs or document_ids,
            )
        else:
            writer = DeterministicWriter()
        result = compose(
            str(template),
            kg=kg,
            topic=topic,
            params=params,
            writer=writer,
        )
        state.compose_result = result.model_dump(by_alias=True, mode="json")
        state.agent = "composer"
        state.delegation_chain = list(
            dict.fromkeys([*state.delegation_chain, "composer"])
        )
        self.store.append_blackboard(
            state.run_id,
            {
                "kind": "compose",
                "template": result.template,
                "citations_map": result.citations_map,
                "unfilled": result.unfilled,
                "provenance": "orchestrator",
                "kg_documents": document_ids,
                "findings_grounded": bool(findings_prose),
            },
        )
        state.status = "succeeded"
        state.ended_at = utc_now_rfc3339()
        self.store.write_state(state)
        self.guard.emit(
            kind="agent.step",
            state=state,
            intent="generate",
            ext={"template": result.template},
            chunk_ids=[
                cid for ids in result.citations_map.values() for cid in ids
            ],
        )
        return state
