"""Single-agent reason→act→observe loop (from scratch)."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Protocol

from thot.action.models import utc_now_rfc3339
from thot.agent.guard import AgentGuard
from thot.agent.models import (
    AgentSpec,
    GroundedFinding,
    GroundedFindings,
    RunState,
    StepRecord,
    ToolCall,
)
from thot.agent.runs import RunStore
from thot.agent.safety import wrap_untrusted
from thot.agent.toolbox import ToolRegistry
from thot.core.ThotMetrics import ThotMetrics
from thot.mcp.authz import McpPrincipal

LOGGER = logging.getLogger(__name__)

_JSON_FENCE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)


class LlmClient(Protocol):
    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.1,
    ) -> str: ...


def parse_agent_message(text: str) -> dict[str, Any]:
    """Parse a strict JSON tool/final block from the model reply.

    Example:
        >>> from thot.agent.loop import parse_agent_message
        >>> parse_agent_message(
        ...     '```json\\n{"tool": "search", "arguments": {"query": "x"}}\\n```'
        ... )["tool"]
        'search'
    """
    match = _JSON_FENCE.search(text or "")
    raw = match.group(1) if match else (text or "").strip()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("agent message must be a JSON object")
    return data


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _findings_from_final(
    payload: dict[str, Any], goal: str
) -> GroundedFindings:
    findings: list[GroundedFinding] = []
    for item in payload.get("findings") or []:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()
        chunk_ids = [str(c) for c in item.get("chunk_ids") or [] if c]
        doc_ids = [str(d) for d in item.get("document_ids") or [] if d]
        if claim and not chunk_ids and not doc_ids:
            # No provenance → move to unfilled rather than hallucinate support
            continue
        if claim:
            findings.append(
                GroundedFinding(
                    claim=claim,
                    chunk_ids=chunk_ids,
                    document_ids=doc_ids,
                    confidence=float(item.get("confidence") or 0.0),
                )
            )
    unfilled = [str(u) for u in payload.get("unfilled") or [] if u]
    # Any claim without provenance already dropped; note if empty
    if not findings and goal:
        unfilled = unfilled or ["no grounded findings"]
    return GroundedFindings(
        goal=goal,
        findings=findings,
        unfilled=unfilled,
        notes=str(payload.get("notes") or ""),
    )


class AgentLoop:
    """Run one agent until final, kill, budget, or max_steps.

    Example:
        >>> from thot.agent.loop import AgentLoop
        >>> AgentLoop  # doctest: +ELLIPSIS
        <class 'thot.agent.loop.AgentLoop'>
    """

    def __init__(
        self,
        *,
        store: RunStore,
        guard: AgentGuard,
        llm: LlmClient,
        toolbox: ToolRegistry | None = None,
    ) -> None:
        self.store = store
        self.guard = guard
        self.llm = llm
        self.toolbox = toolbox

    async def run(
        self,
        state: RunState,
        spec: AgentSpec,
        *,
        authorization: str | None = None,
        step_offset: int = 0,
        finalize: bool = True,
        goal_override: str | None = None,
    ) -> RunState:
        ThotMetrics.create_counter(
            short_name="agent_runs",
            function_name="agent_runs_total",
            counter_description="Agent runs",
        )
        ThotMetrics.increment_counter(
            short_name="agent_runs",
            method="AGENT",
            path="/agent/runs",
            status=200,
        )
        toolbox = self.toolbox or ToolRegistry(spec.tools)
        principal = McpPrincipal(
            user_space=state.user_space,
            scopes=["intent:search", "intent:agent.run", "intent:tool.invoke"],
            subject=state.user_space,
            raw_authorization=authorization,
        )
        if finalize:
            self.guard.mint_run_token(
                actor_id=state.user_space, run_id=state.run_id
            )
            self.guard.emit(kind="agent.plan", state=state, intent="agent.run")
            state.status = "running"
            if not state.started_at:
                state.started_at = utc_now_rfc3339()
            self.store.write_state(state)

        wall_started = time.monotonic()
        history: list[dict[str, Any]] = []
        repair_used = False
        phase_goal = goal_override if goal_override is not None else state.goal

        for local_index in range(spec.stop.max_steps):
            step_index = step_offset + local_index
            decision = self.guard.check_step(
                state, spec, wall_started=wall_started
            )
            if decision.result == "deny":
                state.status = (
                    "killed"
                    if "kill switch" in decision.message
                    else "blocked"
                )
                state.error = decision.message
                state.ended_at = utc_now_rfc3339()
                self.store.write_state(state)
                self.store.move_to_dlq(state.run_id, decision.message)
                self.guard.emit(
                    kind="agent.step",
                    state=state,
                    status="blocked",
                    decision="deny",
                    error=decision.message,
                )
                return state

            ThotMetrics.increment_counter(
                short_name="agent_steps",
                method="AGENT",
                path="/agent/step",
                status=200,
            )
            step = StepRecord(step_index=step_index)
            prompt = self._build_prompt(
                spec, state, history, toolbox, goal=phase_goal
            )
            try:
                raw = await self.llm.generate(
                    prompt,
                    system=spec.system_prompt,
                    temperature=spec.temperature,
                )
            except Exception as exc:  # noqa: BLE001
                step.status = "error"
                step.error = str(exc)
                step.ended_at = utc_now_rfc3339()
                self.store.write_step(state.run_id, step)
                state.status = "failed"
                state.error = str(exc)
                state.ended_at = utc_now_rfc3339()
                self.store.write_state(state)
                self.store.move_to_dlq(state.run_id, str(exc))
                return state

            state.usage.llm_tokens += _estimate_tokens(
                prompt
            ) + _estimate_tokens(raw)
            step.thought_excerpt = (raw or "")[:500]

            try:
                parsed = parse_agent_message(raw)
                repair_used = False
            except (json.JSONDecodeError, ValueError) as exc:
                if not repair_used:
                    repair_used = True
                    history.append(
                        {
                            "role": "assistant",
                            "content": wrap_untrusted(raw, source="model"),
                        }
                    )
                    history.append(
                        {
                            "role": "user",
                            "content": (
                                "Parse error. Reply with a single valid JSON "
                                f"fence only. Error: {exc}"
                            ),
                        }
                    )
                    step.status = "parse_error"
                    step.error = str(exc)
                    step.ended_at = utc_now_rfc3339()
                    self.store.write_step(state.run_id, step)
                    continue
                step.status = "parse_error"
                step.error = f"parse failed after repair: {exc}"
                step.ended_at = utc_now_rfc3339()
                self.store.write_step(state.run_id, step)
                state.status = "failed"
                state.error = step.error
                state.ended_at = utc_now_rfc3339()
                self.store.write_state(state)
                return state

            if parsed.get("final") is True:
                findings = _findings_from_final(parsed, phase_goal)
                step.final = findings
                step.ended_at = utc_now_rfc3339()
                self.store.write_step(state.run_id, step)
                state.result = findings
                state.steps_completed = step_index + 1
                if finalize:
                    state.status = "succeeded"
                    state.ended_at = utc_now_rfc3339()
                self.store.write_state(state)
                self.guard.emit(
                    kind="agent.step",
                    state=state,
                    chunk_ids=[
                        cid
                        for finding in findings.findings
                        for cid in finding.chunk_ids
                    ],
                )
                return state

            tool_name = str(parsed.get("tool") or "")
            arguments = parsed.get("arguments") or {}
            if not tool_name or not isinstance(arguments, dict):
                history.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid tool payload; use tool or final JSON."
                        ),
                    }
                )
                step.status = "parse_error"
                step.error = "missing tool/arguments"
                step.ended_at = utc_now_rfc3339()
                self.store.write_step(state.run_id, step)
                continue

            if self.guard.is_agents_killed() or state.cancel_requested:
                state.status = "killed"
                state.error = "killed before tool invoke"
                state.ended_at = utc_now_rfc3339()
                self.store.write_state(state)
                return state

            step.tool_call = ToolCall(name=tool_name, arguments=arguments)
            try:
                observation = await toolbox.invoke(
                    tool_name,
                    arguments,
                    principal=principal,
                )
                state.usage.tool_calls += 1
                ThotMetrics.increment_counter(
                    short_name="agent_tool_calls",
                    method="AGENT",
                    path=f"/tool/{tool_name}",
                    status=200,
                )
                self.guard.emit(
                    kind="tool.invoke",
                    state=state,
                    intent="tool.invoke",
                    ext={"tool": tool_name},
                    chunk_ids=[
                        str(c.get("chunk_id"))
                        for c in observation.get("chunks") or []
                        if isinstance(c, dict) and c.get("chunk_id")
                    ]
                    or [str(c) for c in observation.get("chunk_ids") or []],
                )
            except Exception as exc:  # noqa: BLE001
                step.status = "error"
                step.error = str(exc)
                step.ended_at = utc_now_rfc3339()
                self.store.write_step(state.run_id, step)
                observation = {
                    "error": str(exc),
                    "_untrusted_view": wrap_untrusted(
                        {"error": str(exc)}, source="tool-error"
                    ),
                }

            step.observation = {
                k: v for k, v in observation.items() if k != "_untrusted_view"
            }
            step.ended_at = utc_now_rfc3339()
            self.store.write_step(state.run_id, step)
            self.store.append_blackboard(
                state.run_id,
                {
                    "step": step_index,
                    "agent": state.agent,
                    "tool": tool_name,
                    "chunk_ids": (
                        [
                            str(c.get("chunk_id"))
                            for c in observation.get("chunks") or []
                            if isinstance(c, dict) and c.get("chunk_id")
                        ]
                        or [str(c) for c in observation.get("chunk_ids") or []]
                    ),
                },
            )
            history.append(
                {
                    "role": "assistant",
                    "content": wrap_untrusted(
                        {"tool": tool_name, "arguments": arguments},
                        source="assistant-tool",
                    ),
                }
            )
            history.append(
                {
                    "role": "user",
                    "content": (
                        observation.get("_untrusted_view")
                        or wrap_untrusted(observation, source=tool_name)
                    ),
                }
            )
            state.steps_completed = step_index + 1
            self.store.write_state(state)

        state.status = "failed"
        state.error = "max_steps exceeded without final"
        state.ended_at = utc_now_rfc3339()
        self.store.write_state(state)
        self.store.move_to_dlq(state.run_id, state.error)
        return state

    def _build_prompt(
        self,
        spec: AgentSpec,
        state: RunState,
        history: list[dict[str, Any]],
        toolbox: ToolRegistry,
        *,
        goal: str | None = None,
    ) -> str:
        tools_json = json.dumps(toolbox.tool_specs_for_prompt(), indent=2)
        hist = "\n\n".join(
            f"{item.get('role')}: {item.get('content')}"
            for item in history[-8:]
        )
        return (
            f"Goal: {goal if goal is not None else state.goal}\n"
            f"user_space: {state.user_space}\n"
            f"Available tools (JSON Schema):\n{tools_json}\n\n"
            f"Recent history:\n{hist or '(none)'}\n\n"
            "Emit the next JSON fence now."
        )
