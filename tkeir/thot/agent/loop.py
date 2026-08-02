"""Title: Loop

Single-agent reason→act→observe loop (from scratch).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

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

_FENCE_START = re.compile(r"```(?:json)?\s*", re.IGNORECASE)


def _extract_balanced_json_object(text: str, *, start: int = 0) -> str | None:
    """Return the first top-level ``{...}`` slice using brace depth (string-aware)."""
    i = text.find("{", start)
    if i < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for j in range(i, len(text)):
        ch = text[j]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[i : j + 1]
    return None


def parse_agent_message(text: str) -> dict[str, Any]:
    """Parse a strict JSON tool/final block from the model reply.

    Example:
        >>> from thot.agent.loop import parse_agent_message
        >>> parse_agent_message(
        ...     '```json\\n{"tool": "search", "arguments": {"query": "x"}}\\n```'
        ... )["tool"]
        'search'
    """
    blob = text or ""
    raw: str | None = None
    fence = _FENCE_START.search(blob)
    if fence is not None:
        raw = _extract_balanced_json_object(blob, start=fence.end())
    if raw is None:
        raw = _extract_balanced_json_object(blob)
    if raw is None:
        raw = blob.strip()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("agent message must be a JSON object")
    return data


class LlmClient(Protocol):
    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.1,
    ) -> str: ...


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _finding_from_item(item: Any) -> GroundedFinding | None:
    if not isinstance(item, dict):
        return None
    claim = str(item.get("claim") or "").strip()
    if not claim:
        return None
    chunk_ids = [str(c) for c in item.get("chunk_ids") or [] if c]
    doc_ids = [str(d) for d in item.get("document_ids") or [] if d]
    if not chunk_ids and not doc_ids:
        # No provenance → move to unfilled rather than hallucinate support
        return None
    return GroundedFinding(
        claim=claim,
        chunk_ids=chunk_ids,
        document_ids=doc_ids,
        confidence=float(item.get("confidence") or 0.0),
    )


def _findings_from_final(
    payload: dict[str, Any], goal: str
) -> GroundedFindings:
    findings: list[GroundedFinding] = []
    for item in payload.get("findings") or []:
        finding = _finding_from_item(item)
        if finding is not None:
            findings.append(finding)
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


def _is_successful_wiki_put(
    tool_name: str, observation: dict[str, Any]
) -> bool:
    """True when okf_wiki_put persisted wiki.md successfully."""
    return (
        tool_name == "okf_wiki_put"
        and isinstance(observation, dict)
        and observation.get("ok") is True
        and not observation.get("error")
    )


def _findings_after_wiki_put(
    state: RunState,
    observation: dict[str, Any],
    *,
    phase_goal: str,
) -> GroundedFindings:
    """Keep reviewed findings; mark wiki persistence in notes/document_ids."""
    notes = f"okf_wiki_put:{observation.get('path') or observation.get('bundle_id') or 'ok'}"
    if state.result and state.result.findings:
        findings = [
            GroundedFinding(
                claim=finding.claim,
                chunk_ids=list(finding.chunk_ids),
                document_ids=list(
                    dict.fromkeys([*finding.document_ids, "okf:wiki"])
                ),
                confidence=finding.confidence,
            )
            for finding in state.result.findings
        ]
        return GroundedFindings(
            goal=phase_goal,
            findings=findings,
            unfilled=list(state.result.unfilled),
            notes=notes,
        )
    return GroundedFindings(
        goal=phase_goal,
        findings=[
            GroundedFinding(
                claim="LLMWiki written answering the query",
                chunk_ids=[],
                document_ids=["okf:wiki"],
                confidence=0.9,
            )
        ],
        unfilled=[],
        notes=notes,
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

    def _emit_agent_runs_metric(self) -> None:
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

    def _prepare_run(
        self,
        state: RunState,
        spec: AgentSpec,
        *,
        authorization: str | None,
        finalize: bool,
    ) -> tuple[ToolRegistry, McpPrincipal]:
        self._emit_agent_runs_metric()
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
        return toolbox, principal

    def _handle_guard_deny(self, state: RunState, decision: Any) -> RunState:
        state.status = (
            "killed" if "kill switch" in decision.message else "blocked"
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

    def _handle_llm_failure(
        self, state: RunState, step: StepRecord, exc: Exception
    ) -> RunState:
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

    def _handle_parse_repair(
        self,
        state: RunState,
        step: StepRecord,
        raw: str,
        exc: Exception,
        history: list[dict[str, Any]],
    ) -> bool:
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
        return True

    def _handle_parse_failure(
        self,
        state: RunState,
        step: StepRecord,
        exc: Exception,
    ) -> RunState:
        step.status = "parse_error"
        step.error = f"parse failed after repair: {exc}"
        step.ended_at = utc_now_rfc3339()
        self.store.write_step(state.run_id, step)
        state.status = "failed"
        state.error = step.error
        state.ended_at = utc_now_rfc3339()
        self.store.write_state(state)
        return state

    def _complete_with_final(
        self,
        state: RunState,
        step: StepRecord,
        parsed: dict[str, Any],
        *,
        phase_goal: str,
        step_index: int,
        finalize: bool,
    ) -> RunState:
        findings = _findings_from_final(parsed, phase_goal)
        return self._finish_with_findings(
            state,
            step,
            findings,
            step_index=step_index,
            finalize=finalize,
        )

    def _complete_after_successful_wiki_put(
        self,
        state: RunState,
        step: StepRecord,
        observation: dict[str, Any],
        *,
        phase_goal: str,
        step_index: int,
        finalize: bool,
    ) -> RunState:
        LOGGER.info(
            "auto-finalizing after successful okf_wiki_put run_id=%s step=%s",
            state.run_id,
            step_index,
        )
        findings = _findings_after_wiki_put(
            state, observation, phase_goal=phase_goal
        )
        return self._finish_with_findings(
            state,
            step,
            findings,
            step_index=step_index,
            finalize=finalize,
        )

    def _finish_with_findings(
        self,
        state: RunState,
        step: StepRecord,
        findings: GroundedFindings,
        *,
        step_index: int,
        finalize: bool,
    ) -> RunState:
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

    def _handle_invalid_tool_payload(
        self,
        state: RunState,
        step: StepRecord,
        history: list[dict[str, Any]],
    ) -> None:
        history.append(
            {
                "role": "user",
                "content": "Invalid tool payload; use tool or final JSON.",
            }
        )
        step.status = "parse_error"
        step.error = "missing tool/arguments"
        step.ended_at = utc_now_rfc3339()
        self.store.write_step(state.run_id, step)

    def _observation_chunk_ids(self, observation: dict[str, Any]) -> list[str]:
        from_chunks = [
            str(c.get("chunk_id"))
            for c in observation.get("chunks") or []
            if isinstance(c, dict) and c.get("chunk_id")
        ]
        if from_chunks:
            return from_chunks
        return [str(c) for c in observation.get("chunk_ids") or []]

    async def _invoke_tool(
        self,
        state: RunState,
        step: StepRecord,
        *,
        toolbox: ToolRegistry,
        tool_name: str,
        arguments: dict[str, Any],
        principal: McpPrincipal,
    ) -> dict[str, Any]:
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
                chunk_ids=self._observation_chunk_ids(observation),
            )
            return observation
        except Exception as exc:  # noqa: BLE001
            step.status = "error"
            step.error = str(exc)
            step.ended_at = utc_now_rfc3339()
            self.store.write_step(state.run_id, step)
            return {
                "error": str(exc),
                "_untrusted_view": wrap_untrusted(
                    {"error": str(exc)}, source="tool-error"
                ),
            }

    def _record_tool_observation(
        self,
        state: RunState,
        step: StepRecord,
        *,
        step_index: int,
        tool_name: str,
        arguments: dict[str, Any],
        observation: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> None:
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
                "chunk_ids": self._observation_chunk_ids(observation),
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

    def _fail_max_steps(self, state: RunState) -> RunState:
        state.status = "failed"
        state.error = "max_steps exceeded without final"
        state.ended_at = utc_now_rfc3339()
        self.store.write_state(state)
        self.store.move_to_dlq(state.run_id, state.error)
        return state

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
        toolbox, principal = self._prepare_run(
            state, spec, authorization=authorization, finalize=finalize
        )

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
                return self._handle_guard_deny(state, decision)

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
                return self._handle_llm_failure(state, step, exc)

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
                    self._handle_parse_repair(state, step, raw, exc, history)
                    continue
                return self._handle_parse_failure(state, step, exc)

            if parsed.get("final") is True:
                return self._complete_with_final(
                    state,
                    step,
                    parsed,
                    phase_goal=phase_goal,
                    step_index=step_index,
                    finalize=finalize,
                )

            tool_name = str(parsed.get("tool") or "")
            arguments = parsed.get("arguments") or {}
            if not tool_name or not isinstance(arguments, dict):
                self._handle_invalid_tool_payload(state, step, history)
                continue

            if self.guard.is_agents_killed() or state.cancel_requested:
                state.status = "killed"
                state.error = "killed before tool invoke"
                state.ended_at = utc_now_rfc3339()
                self.store.write_state(state)
                return state

            observation = await self._invoke_tool(
                state,
                step,
                toolbox=toolbox,
                tool_name=tool_name,
                arguments=arguments,
                principal=principal,
            )
            self._record_tool_observation(
                state,
                step,
                step_index=step_index,
                tool_name=tool_name,
                arguments=arguments,
                observation=observation,
                history=history,
            )
            # okf_wiki_put is a terminal write: models often re-call it instead
            # of emitting final=true after ok:true (burns max_steps).
            if _is_successful_wiki_put(tool_name, observation):
                return self._complete_after_successful_wiki_put(
                    state,
                    step,
                    observation,
                    phase_goal=phase_goal,
                    step_index=step_index,
                    finalize=finalize,
                )

        return self._fail_max_steps(state)

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
        prior = ""
        if state.result and state.result.findings:
            try:
                prior = (
                    "\nPrior grounded findings (JSON):\n"
                    + json.dumps(
                        [
                            f.model_dump(mode="json")
                            for f in state.result.findings
                        ],
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n"
                )
            except Exception:  # noqa: BLE001
                prior = ""
        params_hint = ""
        wiki_block = ""
        if state.params:
            interesting = {
                k: state.params[k]
                for k in (
                    "report_form",
                    "report_form_slots",
                    "bundle_id",
                    "use_existing_wiki",
                    "has_llm_wiki",
                    "topic",
                )
                if k in state.params
            }
            if interesting:
                params_hint = (
                    "\nRun params: "
                    + json.dumps(interesting, ensure_ascii=False)
                    + "\n"
                )
            wiki = str(state.params.get("wiki_markdown") or "").strip()
            if wiki:
                wiki_block = (
                    "\nPRIMARY SOURCE — Phase-2 LLM Wiki (edited; treat as "
                    "authoritative fact base for this report; do not rebuild "
                    "research from scratch):\n"
                    "----- BEGIN LLM WIKI -----\n"
                    f"{wiki}\n"
                    "----- END LLM WIKI -----\n"
                )
        return (
            f"Goal: {goal if goal is not None else state.goal}\n"
            f"user_space: {state.user_space}\n"
            f"{params_hint}"
            f"{wiki_block}"
            f"{prior}"
            f"Available tools (JSON Schema):\n{tools_json}\n\n"
            f"Recent history:\n{hist or '(none)'}\n\n"
            "Emit the next JSON fence now."
        )
