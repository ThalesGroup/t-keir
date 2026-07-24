"""Title: Multi-agent orchestrator from scratch (Phase D) — sequential only.

Supervisor plan comes from ``WorkflowSpec`` YAML. Each agent phase runs the
existing :class:`AgentLoop`; compose phases use ``thot.compose``. Builtin
steps (e.g. OKF scoped export) run in-process helpers. Explicit
:class:`Handoff` records and an append-only blackboard carry provenance.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import logging
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
from thot.compose.demo_data import demo_turtles
from thot.compose.kg import UserSpaceKG
from thot.compose.writers import DeterministicWriter
from thot.core.ThotMetrics import ThotMetrics
from thot.mcp.client import OutboundMcpClient, default_outbound_client
from thot.mcp.handlers import McpHandlers
from thot.okf.applicator import OkfEnrichmentApplicator, enrichments_from_grounded
from thot.okf.exporter import default_okf_root, export_scoped
from thot.okf.models import OkfExportRequest

LOGGER = logging.getLogger(__name__)


def _format_goal(template: str, *, goal: str, params: dict[str, Any]) -> str:
    ctx = {"goal": goal, **params}
    try:
        return template.format(**ctx)
    except (KeyError, ValueError):
        return template.replace("{goal}", goal)


def _chunk_ids_from_state(state: RunState) -> list[str]:
    if state.result is None:
        return []
    out: list[str] = []
    for finding in state.result.findings:
        out.extend(finding.chunk_ids)
    return sorted(set(out))


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
        self.store = store
        self.guard = guard
        self.llm = llm
        self.outbound = outbound or default_outbound_client()
        self.handlers = handlers

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
                if state.status in {"failed", "blocked", "killed", "cancelled"}:
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
        assert wf_step.builtin is not None
        handoff = Handoff(
            from_agent=previous_agent,
            to_agent=f"builtin:{wf_step.builtin}",
            reason=f"workflow:{workflow.name}:{wf_step.id}",
            payload_summary=wf_step.builtin,
            chunk_ids=_chunk_ids_from_state(state),
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
                "chunk_ids": handoff.chunk_ids,
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
            chunk_ids=handoff.chunk_ids,
        )

        if wf_step.builtin == "okf_scoped_export":
            state = await self._run_okf_scoped_export(state, wf_step)
        else:
            state.status = "failed"
            state.error = f"unknown builtin step: {wf_step.builtin!r}"
            state.ended_at = utc_now_rfc3339()
            self.store.write_state(state)
        return state

    async def _run_okf_scoped_export(
        self, state: RunState, wf_step: WorkflowStep
    ) -> RunState:
        params = dict(state.params or {})
        for key in wf_step.params_from:
            if key not in params and key == "query":
                params["query"] = state.goal
            if key not in params and key == "topic":
                params["topic"] = params.get("topic") or state.goal
        query = str(params.get("query") or params.get("topic") or state.goal)
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
        out_key = wf_step.output_key or "bundle_id"
        state.params = {**params, out_key: result.bundle.bundle_id}
        self.store.append_blackboard(
            state.run_id,
            {
                "kind": "builtin",
                "builtin": "okf_scoped_export",
                "bundle_id": result.bundle.bundle_id,
                "path": result.bundle.path,
                "concept_count": result.bundle.concept_count,
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
        bundle_id = str((state.params or {}).get("bundle_id") or "")
        if not bundle_id or state.result is None:
            return
        root = default_okf_root() / bundle_id
        if not root.is_dir():
            bb = self.store.blackboard_path(state.run_id)
            if bb.is_file():
                data = json.loads(bb.read_text(encoding="utf-8"))
                for entry in data.get("entries") or []:
                    if (
                        entry.get("bundle_id") == bundle_id
                        and entry.get("path")
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
            chunk_ids=_chunk_ids_from_state(state),
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
                "chunk_ids": handoff.chunk_ids,
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
            chunk_ids=handoff.chunk_ids,
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
        compose_cfg = wf_step.compose
        assert compose_cfg is not None
        template = (
            compose_cfg.template
            or workflow.template
            or state.params.get("template")
            or "synthesis_note"
        )
        topic_key = compose_cfg.topic_from or "goal"
        topic = str(
            state.params.get(topic_key)
            or state.params.get("topic")
            or state.goal
        )
        kg = UserSpaceKG(state.user_space, use_process_cache=False)
        kg.load(demo_turtles(), document_ids=["doc_a"])
        short_topic = str(state.params.get("topic") or topic.split()[-1])
        result = compose(
            str(template),
            kg=kg,
            topic=short_topic,
            writer=DeterministicWriter(),
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
