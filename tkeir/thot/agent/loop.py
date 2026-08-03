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
    """Return the first top-level ``{...}`` slice using brace depth (string-aware).

    Args:
        text: Source text that may contain a JSON object.
        start: Index at which to begin searching for ``{``.

    Returns:
        The balanced object substring, or ``None`` when no complete object exists.

    Example:
        >>> from thot.agent.loop import _extract_balanced_json_object
        >>> _extract_balanced_json_object('prefix {"a": 1} suffix')
        '{"a": 1}'
        >>> _extract_balanced_json_object('no braces') is None
        True
    """
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
    """Minimal async LLM surface used by :class:`AgentLoop`.

    Example:
        >>> import inspect
        >>> from thot.agent.loop import LlmClient
        >>> inspect.isclass(LlmClient) or hasattr(LlmClient, "generate")
        True
    """

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.1,
    ) -> str:
        """Generate a completion for ``prompt`` (implemented by LLM backends).

        Args:
            prompt: User / turn prompt text.
            system: Optional system instruction.
            temperature: Sampling temperature.

        Returns:
            Model completion string.

        Example:
            >>> import inspect
            >>> from thot.agent.loop import LlmClient
            >>> inspect.iscoroutinefunction(LlmClient.generate)
            True
        """
        ...


def _estimate_tokens(text: str) -> int:
    """Rough token estimate from character length (÷4, minimum 1).

    Args:
        text: Prompt or completion text.

    Returns:
        Estimated token count (always at least 1).

    Example:
        >>> from thot.agent.loop import _estimate_tokens
        >>> _estimate_tokens("")
        1
        >>> _estimate_tokens("a" * 8)
        2
    """
    return max(1, len(text) // 4)


def _finding_from_item(item: Any) -> GroundedFinding | None:
    """Parse one grounded finding dict; drop claims without provenance.

    Args:
        item: Raw finding payload from a ``final`` JSON block.

    Returns:
        A :class:`~thot.agent.models.GroundedFinding`, or ``None`` when invalid.

    Example:
        >>> from thot.agent.loop import _finding_from_item
        >>> f = _finding_from_item({"claim": "x", "chunk_ids": ["c1"]})
        >>> f.claim if f else None
        'x'
        >>> _finding_from_item({"claim": "no prov"}) is None
        True
    """
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
    """Build :class:`~thot.agent.models.GroundedFindings` from a final payload.

    Args:
        payload: Parsed ``final=true`` JSON object from the model.
        goal: Run or phase goal string stored on the result.

    Returns:
        Grounded findings with unfilled notes when nothing parsed.

    Example:
        >>> from thot.agent.loop import _findings_from_final
        >>> out = _findings_from_final(
        ...     {"findings": [{"claim": "x", "chunk_ids": ["c1"]}]},
        ...     "goal",
        ... )
        >>> len(out.findings)
        1
    """
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
    """True when ``okf_wiki_put`` persisted wiki.md successfully.

    Args:
        tool_name: Invoked tool name from the agent message.
        observation: Tool observation dict returned by the registry.

    Returns:
        ``True`` only for a successful ``okf_wiki_put`` with ``ok: true``.

    Example:
        >>> from thot.agent.loop import _is_successful_wiki_put
        >>> _is_successful_wiki_put("okf_wiki_put", {"ok": True})
        True
        >>> _is_successful_wiki_put("search", {"ok": True})
        False
    """
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
    """Keep reviewed findings; mark wiki persistence in notes/document_ids.

    Args:
        state: Current run state (may already hold prior findings).
        observation: Successful ``okf_wiki_put`` observation dict.
        phase_goal: Goal string for the auto-finalized result.

    Returns:
        Findings annotated with ``okf:wiki`` provenance and wiki notes.

    Example:
        >>> from thot.agent.loop import _findings_after_wiki_put
        >>> from thot.agent.models import RunState, GroundedFindings, GroundedFinding
        >>> state = RunState(
        ...     goal="g",
        ...     result=GroundedFindings(
        ...         findings=[GroundedFinding(claim="x", chunk_ids=["c1"])]
        ...     ),
        ... )
        >>> out = _findings_after_wiki_put(
        ...     state, {"ok": True, "path": "/w"}, phase_goal="g",
        ... )
        >>> "okf:wiki" in out.findings[0].document_ids
        True
    """
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
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.agent.loop import AgentLoop
        >>> from thot.agent.guard import AgentGuard
        >>> from thot.agent.runs import RunStore
        >>> class _StubLlm:
        ...     async def generate(self, prompt, **kw):
        ...         return '{"final": true, "findings": []}'
        >>> with tempfile.TemporaryDirectory() as td:
        ...     root = Path(td)
        ...     loop = AgentLoop(
        ...         store=RunStore(root),
        ...         guard=AgentGuard(root / "gov"),
        ...         llm=_StubLlm(),
        ...     )
        ...     loop.store.root == root
        True
    """

    def __init__(
        self,
        *,
        store: RunStore,
        guard: AgentGuard,
        llm: LlmClient,
        toolbox: ToolRegistry | None = None,
    ) -> None:
        """Wire run store, guard, LLM client, and optional tool registry.

        Args:
            store: Filesystem run store for state and steps.
            guard: Governor guard for budgets and audit emits.
            llm: Async LLM client implementing :class:`LlmClient`.
            toolbox: Optional pre-built registry; defaults per agent spec.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.loop import AgentLoop
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.runs import RunStore
            >>> class _StubLlm:
            ...     async def generate(self, prompt, **kw):
            ...         return '{}'
            >>> with tempfile.TemporaryDirectory() as td:
            ...     loop = AgentLoop(
            ...         store=RunStore(Path(td)),
            ...         guard=AgentGuard(Path(td) / "gov"),
            ...         llm=_StubLlm(),
            ...     )
            ...     loop.guard.root.name
            'gov'
        """
        self.store = store
        self.guard = guard
        self.llm = llm
        self.toolbox = toolbox

    def _emit_agent_runs_metric(self) -> None:
        """Increment the ``agent_runs`` Prometheus counter once per run prep.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.loop import AgentLoop
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.runs import RunStore
            >>> class _StubLlm:
            ...     async def generate(self, prompt, **kw):
            ...         return '{}'
            >>> with tempfile.TemporaryDirectory() as td:
            ...     loop = AgentLoop(
            ...         store=RunStore(Path(td)),
            ...         guard=AgentGuard(Path(td) / "gov"),
            ...         llm=_StubLlm(),
            ...     )
            ...     loop._emit_agent_runs_metric() is None
            True
        """
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
        """Mint tokens, emit plan audit, and build toolbox/principal for a run.

        Args:
            state: Mutable run state persisted when ``finalize`` is true.
            spec: Loaded agent specification (tools, budgets, prompts).
            authorization: Optional raw Authorization header for MCP principal.
            finalize: When true, mark run running and write initial state.

        Returns:
            Tuple of tool registry and MCP principal for tool invocation.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.loop import AgentLoop
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.runs import RunStore
            >>> from thot.agent.models import RunState, AgentSpec
            >>> class _StubLlm:
            ...     async def generate(self, prompt, **kw):
            ...         return '{}'
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.ensure_layout()
            ...     loop = AgentLoop(
            ...         store=store,
            ...         guard=AgentGuard(Path(td) / "gov"),
            ...         llm=_StubLlm(),
            ...     )
            ...     state = RunState(goal="g", user_space="alice")
            ...     spec = AgentSpec(name="researcher", tools=["search"])
            ...     toolbox, principal = loop._prepare_run(
            ...         state, spec, authorization=None, finalize=False,
            ...     )
            ...     principal.user_space
            'alice'
        """
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
        """Persist a blocked/killed run after a guard deny decision.

        Args:
            state: Run state updated in place and written to the store.
            decision: :class:`~thot.agent.guard.GuardDecision` with deny message.

        Returns:
            The updated run state (also moved to DLQ when denied).

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.loop import AgentLoop
            >>> from thot.agent.guard import AgentGuard, GuardDecision
            >>> from thot.agent.runs import RunStore
            >>> from thot.agent.models import RunState
            >>> class _StubLlm:
            ...     async def generate(self, prompt, **kw):
            ...         return '{}'
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.ensure_layout()
            ...     loop = AgentLoop(
            ...         store=store,
            ...         guard=AgentGuard(Path(td) / "gov"),
            ...         llm=_StubLlm(),
            ...     )
            ...     state = RunState(goal="g")
            ...     _ = store.write_state(state)
            ...     dec = GuardDecision(
            ...         result="deny",
            ...         message="kill switch scope=agents is active",
            ...     )
            ...     out = loop._handle_guard_deny(state, dec)
            ...     out.status
            'killed'
        """
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
        """Mark step and run failed after an LLM client error.

        Args:
            state: Run state written as ``failed`` and moved to DLQ.
            step: Step record persisted with ``error`` status.
            exc: Exception raised by :meth:`LlmClient.generate`.

        Returns:
            Updated failed run state.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.loop import AgentLoop
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.runs import RunStore
            >>> from thot.agent.models import RunState, StepRecord
            >>> class _StubLlm:
            ...     async def generate(self, prompt, **kw):
            ...         return '{}'
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.ensure_layout()
            ...     loop = AgentLoop(
            ...         store=store,
            ...         guard=AgentGuard(Path(td) / "gov"),
            ...         llm=_StubLlm(),
            ...     )
            ...     state = RunState(goal="g")
            ...     _ = store.write_state(state)
            ...     step = StepRecord(step_index=0)
            ...     out = loop._handle_llm_failure(state, step, RuntimeError("boom"))
            ...     out.status
            'failed'
        """
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
        """Append repair prompts to history and persist a parse_error step.

        Args:
            state: Run whose step is written to the store.
            step: Step marked ``parse_error`` with the parse exception message.
            raw: Raw model output wrapped as untrusted assistant content.
            exc: JSON or schema parse error triggering repair.
            history: Mutable conversation history extended in place.

        Returns:
            Always ``True`` (signals the loop to retry the step).

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.loop import AgentLoop
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.runs import RunStore
            >>> from thot.agent.models import RunState, StepRecord
            >>> class _StubLlm:
            ...     async def generate(self, prompt, **kw):
            ...         return '{}'
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.ensure_layout()
            ...     loop = AgentLoop(
            ...         store=store,
            ...         guard=AgentGuard(Path(td) / "gov"),
            ...         llm=_StubLlm(),
            ...     )
            ...     state = RunState(goal="g")
            ...     _ = store.write_state(state)
            ...     step = StepRecord(step_index=0)
            ...     hist = []
            ...     ok = loop._handle_parse_repair(
            ...         state, step, "bad", ValueError("x"), hist,
            ...     )
            ...     ok and len(hist) == 2
            True
        """
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
        """Fail the run after a second consecutive parse error.

        Args:
            state: Run marked ``failed`` without DLQ move (repair already tried).
            step: Step persisted with combined parse failure message.
            exc: Final parse exception.

        Returns:
            Updated failed run state.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.loop import AgentLoop
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.runs import RunStore
            >>> from thot.agent.models import RunState, StepRecord
            >>> class _StubLlm:
            ...     async def generate(self, prompt, **kw):
            ...         return '{}'
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.ensure_layout()
            ...     loop = AgentLoop(
            ...         store=store,
            ...         guard=AgentGuard(Path(td) / "gov"),
            ...         llm=_StubLlm(),
            ...     )
            ...     state = RunState(goal="g")
            ...     _ = store.write_state(state)
            ...     step = StepRecord(step_index=0)
            ...     out = loop._handle_parse_failure(state, step, ValueError("x"))
            ...     out.status
            'failed'
        """
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
        """Finalize a step when the model emits ``final: true``.

        Args:
            state: Run receiving grounded findings as ``result``.
            step: Step record holding the parsed final payload.
            parsed: Parsed agent JSON with ``findings`` / ``unfilled``.
            phase_goal: Goal string stored on the findings contract.
            step_index: Zero-based step index for completion counters.
            finalize: When true, mark run ``succeeded`` and set ``ended_at``.

        Returns:
            Updated run state after :meth:`_finish_with_findings`.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.loop import AgentLoop
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.runs import RunStore
            >>> from thot.agent.models import RunState, StepRecord
            >>> class _StubLlm:
            ...     async def generate(self, prompt, **kw):
            ...         return '{}'
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.ensure_layout()
            ...     loop = AgentLoop(
            ...         store=store,
            ...         guard=AgentGuard(Path(td) / "gov"),
            ...         llm=_StubLlm(),
            ...     )
            ...     state = RunState(goal="g")
            ...     _ = store.write_state(state)
            ...     step = StepRecord(step_index=0)
            ...     parsed = {
            ...         "final": True,
            ...         "findings": [{"claim": "x", "chunk_ids": ["c1"]}],
            ...     }
            ...     out = loop._complete_with_final(
            ...         state, step, parsed, phase_goal="g", step_index=0, finalize=True,
            ...     )
            ...     out.status
            'succeeded'
        """
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
        """Auto-finalize after a successful ``okf_wiki_put`` tool observation.

        Args:
            state: Run receiving wiki-annotated findings.
            step: Step that invoked ``okf_wiki_put``.
            observation: Tool result dict with ``ok: true``.
            phase_goal: Goal string for the synthesized findings.
            step_index: Current step index for completion counters.
            finalize: When true, mark run ``succeeded``.

        Returns:
            Updated run state after :meth:`_finish_with_findings`.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.loop import AgentLoop
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.runs import RunStore
            >>> from thot.agent.models import RunState, StepRecord
            >>> class _StubLlm:
            ...     async def generate(self, prompt, **kw):
            ...         return '{}'
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.ensure_layout()
            ...     loop = AgentLoop(
            ...         store=store,
            ...         guard=AgentGuard(Path(td) / "gov"),
            ...         llm=_StubLlm(),
            ...     )
            ...     state = RunState(goal="g")
            ...     _ = store.write_state(state)
            ...     step = StepRecord(step_index=0)
            ...     out = loop._complete_after_successful_wiki_put(
            ...         state, step, {"ok": True, "path": "/w"},
            ...         phase_goal="g", step_index=0, finalize=True,
            ...     )
            ...     out.status
            'succeeded'
        """
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
        """Persist findings on the step/run and emit a guard audit record.

        Args:
            state: Run updated with ``result`` and optional terminal status.
            step: Step receiving ``final`` findings and ``ended_at``.
            findings: Grounded output contract for this phase.
            step_index: Step index stored as ``steps_completed``.
            finalize: When true, set run status to ``succeeded``.

        Returns:
            Updated run state written to the store.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.loop import AgentLoop
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.runs import RunStore
            >>> from thot.agent.models import RunState, StepRecord, GroundedFindings, GroundedFinding
            >>> class _StubLlm:
            ...     async def generate(self, prompt, **kw):
            ...         return '{}'
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.ensure_layout()
            ...     loop = AgentLoop(
            ...         store=store,
            ...         guard=AgentGuard(Path(td) / "gov"),
            ...         llm=_StubLlm(),
            ...     )
            ...     state = RunState(goal="g")
            ...     _ = store.write_state(state)
            ...     step = StepRecord(step_index=0)
            ...     findings = GroundedFindings(
            ...         findings=[GroundedFinding(claim="x", chunk_ids=["c1"])]
            ...     )
            ...     out = loop._finish_with_findings(
            ...         state, step, findings, step_index=0, finalize=True,
            ...     )
            ...     out.result.findings[0].claim
            'x'
        """
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
        """Record a parse_error step and nudge the model to fix tool JSON.

        Args:
            state: Run whose step is persisted.
            step: Step marked ``parse_error`` for missing tool/arguments.
            history: Conversation history appended with a user repair hint.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.loop import AgentLoop
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.runs import RunStore
            >>> from thot.agent.models import RunState, StepRecord
            >>> class _StubLlm:
            ...     async def generate(self, prompt, **kw):
            ...         return '{}'
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.ensure_layout()
            ...     loop = AgentLoop(
            ...         store=store,
            ...         guard=AgentGuard(Path(td) / "gov"),
            ...         llm=_StubLlm(),
            ...     )
            ...     state = RunState(goal="g")
            ...     _ = store.write_state(state)
            ...     step = StepRecord(step_index=0)
            ...     hist = []
            ...     loop._handle_invalid_tool_payload(state, step, hist)
            ...     step.status
            'parse_error'
        """
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
        """Extract chunk ids from a tool observation for audit provenance.

        Args:
            observation: Tool result dict (``chunks`` or ``chunk_ids`` keys).

        Returns:
            List of chunk id strings, possibly empty.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.loop import AgentLoop
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.runs import RunStore
            >>> class _StubLlm:
            ...     async def generate(self, prompt, **kw):
            ...         return '{}'
            >>> with tempfile.TemporaryDirectory() as td:
            ...     loop = AgentLoop(
            ...         store=RunStore(Path(td)),
            ...         guard=AgentGuard(Path(td) / "gov"),
            ...         llm=_StubLlm(),
            ...     )
            ...     loop._observation_chunk_ids({"chunks": [{"chunk_id": "c1"}]})
            ['c1']
        """
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
        """Execute one allow-listed tool and emit guard/metrics side effects.

        Args:
            state: Run whose tool-call budget is incremented on success.
            step: Step receiving ``tool_call`` and optional error status.
            toolbox: Registry used to invoke the tool asynchronously.
            tool_name: Parsed tool name from the model message.
            arguments: Parsed tool arguments (tenant overrides stripped).
            principal: MCP principal forwarded to the tool handler.

        Returns:
            Tool observation dict (errors include ``_untrusted_view``).

        Example:
            >>> import inspect
            >>> from thot.agent.loop import AgentLoop
            >>> inspect.iscoroutinefunction(AgentLoop._invoke_tool)
            True
        """
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
        """Persist tool observation, blackboard entry, and history turns.

        Args:
            state: Run updated with ``steps_completed`` and written to store.
            step: Step receiving scrubbed observation (no ``_untrusted_view``).
            step_index: Index recorded on the blackboard event.
            tool_name: Invoked tool name for history and blackboard.
            arguments: Tool arguments echoed into assistant history.
            observation: Raw tool result including optional untrusted view.
            history: Mutable conversation history extended in place.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.loop import AgentLoop
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.runs import RunStore
            >>> from thot.agent.models import RunState, StepRecord
            >>> class _StubLlm:
            ...     async def generate(self, prompt, **kw):
            ...         return '{}'
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.ensure_layout()
            ...     loop = AgentLoop(
            ...         store=store,
            ...         guard=AgentGuard(Path(td) / "gov"),
            ...         llm=_StubLlm(),
            ...     )
            ...     state = RunState(goal="g")
            ...     _ = store.write_state(state)
            ...     step = StepRecord(step_index=0)
            ...     hist = []
            ...     loop._record_tool_observation(
            ...         state, step, step_index=0, tool_name="search",
            ...         arguments={"query": "q"},
            ...         observation={"chunks": [{"chunk_id": "c1"}]},
            ...         history=hist,
            ...     )
            ...     state.steps_completed
            1
        """
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
        """Mark the run failed when the step budget is exhausted.

        Args:
            state: Run written as ``failed`` and moved to DLQ.

        Returns:
            Updated run state with ``max_steps exceeded without final`` error.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.loop import AgentLoop
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.runs import RunStore
            >>> from thot.agent.models import RunState
            >>> class _StubLlm:
            ...     async def generate(self, prompt, **kw):
            ...         return '{}'
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.ensure_layout()
            ...     loop = AgentLoop(
            ...         store=store,
            ...         guard=AgentGuard(Path(td) / "gov"),
            ...         llm=_StubLlm(),
            ...     )
            ...     state = RunState(goal="g")
            ...     out = loop._fail_max_steps(state)
            ...     out.status
            'failed'
        """
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
        """Execute the reason→act→observe loop until terminal condition.

        Args:
            state: Mutable run state persisted throughout the loop.
            spec: Agent specification (tools, budgets, prompts, stop).
            authorization: Optional Authorization header for MCP principal.
            step_offset: Base index when continuing a multi-phase workflow.
            finalize: When true, mark run succeeded on final/wiki completion.
            goal_override: Optional phase goal replacing ``state.goal``.

        Returns:
            Terminal run state (succeeded, failed, killed, or blocked).

        Example:
            >>> import inspect
            >>> from thot.agent.loop import AgentLoop
            >>> inspect.iscoroutinefunction(AgentLoop.run)
            True
        """
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
        """Assemble the user prompt for the next LLM turn.

        Args:
            spec: Agent spec supplying system prompt metadata (unused here).
            state: Run state (goal, params, prior findings, wiki block).
            history: Recent conversation turns included in the prompt tail.
            toolbox: Registry whose tool schemas are embedded as JSON.
            goal: Optional override for the displayed goal line.

        Returns:
            Multi-section prompt string ending with an emit-json instruction.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.loop import AgentLoop
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.runs import RunStore
            >>> from thot.agent.models import RunState, AgentSpec
            >>> from thot.agent.toolbox import ToolRegistry
            >>> class _StubLlm:
            ...     async def generate(self, prompt, **kw):
            ...         return '{}'
            >>> with tempfile.TemporaryDirectory() as td:
            ...     loop = AgentLoop(
            ...         store=RunStore(Path(td)),
            ...         guard=AgentGuard(Path(td) / "gov"),
            ...         llm=_StubLlm(),
            ...     )
            ...     state = RunState(goal="investigate")
            ...     spec = AgentSpec(name="researcher", tools=["search"])
            ...     prompt = loop._build_prompt(
            ...         spec, state, [], ToolRegistry(["search"]),
            ...     )
            ...     "Goal: investigate" in prompt
            True
        """
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
