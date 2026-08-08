"""Title: Guard

Governor integration for agent runs: kill switch, budgets, ActionRecords.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from thot.action.models import (
    ActionContext,
    ActionRecord,
    ActorInfo,
    ContextVersions,
    DecisionInfo,
    ExecutionInfo,
    IntentInfo,
    ResultInfo,
    sha256_hex,
    utc_now_rfc3339,
)
from thot.action.sink import default_action_sink
from thot.agent.base import BaseAgentGuard
from thot.agent.models import AgentSpec, RunState
from thot.agent.spiffe import (
    is_allowed_agent_spiffe_id,
    resolve_agent_spiffe_id,
    spiffe_enforce,
)
from thot.core.StructuredLogging import log_structured
from thot.core.ThotMetrics import ThotMetrics
from thot.governor.approvals import ApprovalQueue
from thot.governor.flags import RuntimeFlagsStore
from thot.governor.tokens import ActionTokenService

_METRICS = False


def _ensure_metrics() -> None:
    """Register agent Prometheus counters once per process (idempotent).

    Example:
        >>> from thot.agent.guard import _ensure_metrics
        >>> _ensure_metrics()
        >>> _ensure_metrics()
    """
    global _METRICS
    if _METRICS:
        return
    for short, fn, desc in (
        ("agent_runs", "agent_runs_total", "Agent runs started"),
        ("agent_steps", "agent_steps_total", "Agent loop steps"),
        ("agent_tool_calls", "agent_tool_calls_total", "Agent tool calls"),
        (
            "agent_budget_blocks",
            "agent_budget_blocks_total",
            "Agent budget blocks",
        ),
    ):
        ThotMetrics.create_counter(
            short_name=short, function_name=fn, counter_description=desc
        )
    _METRICS = True


@dataclass
class GuardDecision:
    """Outcome of a pre-step / pre-tool guard check.

    Example:
        >>> from thot.agent.guard import GuardDecision
        >>> GuardDecision(result="allow").result
        'allow'
    """

    result: Literal["allow", "deny", "escalate"] = "allow"
    message: str = ""
    approval_id: str | None = None


@dataclass
class AgentGuard(BaseAgentGuard[RunState, dict[str, Any]]):
    """Per-process guard shared by the agent service (SPIFFE + governor).

    Implements :class:`~thot.agent.base.BaseAgentGuard` while preserving the
    existing ``check_step`` / ``emit`` APIs used by :class:`AgentLoop`.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.agent.guard import AgentGuard
        >>> with tempfile.TemporaryDirectory() as td:
        ...     g = AgentGuard(Path(td))
        ...     g.is_agents_killed()
        False
    """

    root: Path
    mode: str = field(
        default_factory=lambda: (
            os.getenv("GOVERNOR_MODE") or "observe"
        ).lower()
    )
    throttle_ratio: float = 0.8

    def __post_init__(self) -> None:
        """Create governor stores under ``root`` after dataclass init.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.guard import AgentGuard
            >>> with tempfile.TemporaryDirectory() as td:
            ...     g = AgentGuard(Path(td))
            ...     g.flags.path.name
            'flags.json'
        """
        self.root.mkdir(parents=True, exist_ok=True)
        self.flags = RuntimeFlagsStore(self.root / "flags.json")
        self.approvals = ApprovalQueue(self.root / "approvals.json")
        self.tokens = ActionTokenService(
            revoke_path=self.root / "revoked.json"
        )

    def is_agents_killed(self) -> bool:
        """Return whether the agents kill-switch flag is active.

        Returns:
            ``True`` when governor flags mark scope ``agents`` killed.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.guard import AgentGuard
            >>> with tempfile.TemporaryDirectory() as td:
            ...     g = AgentGuard(Path(td))
            ...     g.is_agents_killed()
            False
        """
        return self.flags.is_killed("agents")

    def mint_run_token(self, *, actor_id: str, run_id: str) -> str:
        """Mint a short-lived action token (TTL ≤ 300s).

        Args:
            actor_id: User or tenant id bound to the token.
            run_id: Run id stored in token constraints.

        Returns:
            Compact serialized token string for downstream verification.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.guard import AgentGuard
            >>> with tempfile.TemporaryDirectory() as td:
            ...     g = AgentGuard(Path(td))
            ...     token = g.mint_run_token(actor_id="alice", run_id="run-1")
            ...     isinstance(token, str) and len(token) > 0
            True
        """
        compact, _token = self.tokens.mint(
            actor_id=actor_id,
            intent="agent.run",
            audience="tkeir-agent",
            max_budget=0.0,
            ttl=300,
            constraints={"run_id": run_id},
        )
        return compact

    def check_step(
        self,
        state: RunState,
        spec: AgentSpec,
        *,
        wall_started: float,
    ) -> GuardDecision:
        """Kill-switch + budget gate before each loop step.

        Args:
            state: Run whose usage counters and SPIFFE id may be updated.
            spec: Agent spec supplying budget limits.
            wall_started: ``time.monotonic()`` value when the run began.

        Returns:
            :class:`GuardDecision` with ``allow``, ``deny``, or ``escalate``.

        Example:
            >>> import tempfile
            >>> import time
            >>> from pathlib import Path
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.models import RunState, AgentSpec
            >>> with tempfile.TemporaryDirectory() as td:
            ...     g = AgentGuard(Path(td))
            ...     state = RunState(goal="g", user_space="alice")
            ...     spec = AgentSpec(name="researcher")
            ...     dec = g.check_step(state, spec, wall_started=time.monotonic())
            ...     dec.result
            'allow'
        """
        _ensure_metrics()
        if state.cancel_requested:
            return GuardDecision(result="deny", message="cancel requested")
        if self.is_agents_killed():
            return GuardDecision(
                result="deny",
                message="kill switch scope=agents is active",
            )
        if not state.spiffe_id:
            state.spiffe_id = resolve_agent_spiffe_id(state.agent)
        if spiffe_enforce() and not is_allowed_agent_spiffe_id(
            state.spiffe_id
        ):
            return GuardDecision(
                result="deny",
                message=(
                    "agent SPIFFE identity missing or not allowed "
                    f"(spiffe_id={state.spiffe_id!r})"
                ),
            )
        elapsed = time.monotonic() - wall_started
        state.usage.wall_seconds = elapsed
        limits = spec.budgets

        checks = [
            ("tool_calls", state.usage.tool_calls, limits.tool_calls),
            ("llm_tokens", state.usage.llm_tokens, limits.llm_tokens),
            ("wall_seconds", int(elapsed), limits.wall_seconds),
        ]
        for unit, consumed, limit in checks:
            if limit <= 0:
                continue
            ratio = consumed / limit
            if ratio >= 1.0:
                ThotMetrics.increment_counter(
                    short_name="agent_budget_blocks",
                    method="AGENT",
                    path=f"/budget/{unit}",
                    status=429,
                )
                item = self.approvals.enqueue(
                    correlation_id=state.correlation_id or ("0" * 32),
                    actor_id=state.user_space,
                    intent="agent.run",
                    reason=f"budget exhausted: {unit} {consumed}/{limit}",
                )
                if self.mode == "enforce":
                    return GuardDecision(
                        result="deny",
                        message=f"budget blocked ({unit})",
                        approval_id=item.approval_id,
                    )
                return GuardDecision(
                    result="escalate",
                    message=f"budget throttle/observe ({unit})",
                    approval_id=item.approval_id,
                )
            if ratio >= self.throttle_ratio and self.mode == "enforce":
                # soft throttle: still allow but record
                pass
        return GuardDecision(result="allow")

    def validate_identity(self, identity_token: Any) -> bool:
        """SPIFFE / workload identity check (:class:`BaseAgentGuard`).

        Args:
            identity_token: SPIFFE id string, or ``None`` when unset.

        Returns:
            ``True`` when enforcement is off, or the id is allow-listed.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.guard import AgentGuard
            >>> with tempfile.TemporaryDirectory() as td:
            ...     g = AgentGuard(Path(td))
            ...     g.validate_identity(None) in (True, False)
            True
        """
        if not spiffe_enforce():
            return True
        if identity_token is None or identity_token == "":
            return False
        return is_allowed_agent_spiffe_id(str(identity_token))

    def check_action_permission(
        self, state: RunState, proposed_action: dict[str, Any]
    ) -> bool:
        """Authorize a proposed tool/final action before execution.

        Args:
            state: Current run state (cancel / kill / SPIFFE).
            proposed_action: Action dict (``type``, ``tool``, …).

        Returns:
            ``False`` when cancel, kill-switch, or SPIFFE deny applies.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.models import RunState
            >>> with tempfile.TemporaryDirectory() as td:
            ...     g = AgentGuard(Path(td))
            ...     g.check_action_permission(
            ...         RunState(goal="g"), {"type": "final"}
            ...     )
            True
        """
        if state.cancel_requested:
            return False
        if self.is_agents_killed():
            return False
        if not state.spiffe_id:
            state.spiffe_id = resolve_agent_spiffe_id(state.agent)
        if spiffe_enforce() and not is_allowed_agent_spiffe_id(
            state.spiffe_id
        ):
            return False
        # Tool name may be used by future scoped policies; accept for now.
        _ = proposed_action.get("type") or proposed_action.get("tool")
        return True

    def emit(
        self,
        *,
        kind: str,
        state: RunState,
        intent: str = "agent.run",
        status: str = "success",
        decision: str = "allow",
        error: str | None = None,
        ext: dict[str, Any] | None = None,
        chunk_ids: list[str] | None = None,
    ) -> ActionRecord:
        """Append an ActionRecord for plan/step/tool/handoff.

        Args:
            kind: Audit action kind (e.g. ``agent.plan``, ``tool.invoke``).
            state: Run supplying correlation, actor, and SPIFFE metadata.
            intent: Declared intent stored on the action record.
            status: Execution status string for the audit trail.
            decision: Policy decision label (``allow`` / ``deny``).
            error: Optional error message on failure paths.
            ext: Extra key/value pairs merged into record ``ext``.
            chunk_ids: Provenance chunk ids attached to the result.

        Returns:
            The appended :class:`~thot.action.models.ActionRecord`.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.models import RunState
            >>> with tempfile.TemporaryDirectory() as td:
            ...     g = AgentGuard(Path(td))
            ...     state = RunState(goal="g", user_space="alice")
            ...     rec = g.emit(kind="agent.plan", state=state)
            ...     rec.ext["action_kind"]
            'agent.plan'
        """
        if not state.spiffe_id:
            state.spiffe_id = resolve_agent_spiffe_id(state.agent)
        merged_ext = {
            "action_kind": kind,
            "run_id": state.run_id,
            "user_space": state.user_space,
            "agent": state.agent,
            "spiffe_id": state.spiffe_id,
            **(ext or {}),
        }
        # Prefer concrete tool name when present; otherwise the audit kind.
        action_name = str(
            merged_ext.get("tool") or merged_ext.get("action") or kind
        )
        record = ActionRecord(
            correlation_id=state.correlation_id or ("0" * 32),
            actor=ActorInfo(
                type="agent",
                id=state.user_space,
                spiffe_id=state.spiffe_id,
            ),
            intent=IntentInfo(declared=intent, scope_source="manual"),
            context=ActionContext(
                env=os.getenv("TKEIR_ENV", "dev"),
                service=os.getenv("TKEIR_SERVICE", "tkeir-agent"),
                versions=ContextVersions(app=os.getenv("TKEIR_VERSION", "")),
                request_hash=sha256_hex(f"{state.run_id}:{kind}"),
            ),
            decision=DecisionInfo(
                policy_result=decision,  # type: ignore[arg-type]
                rules_fired=[f"agent.{kind}"],
            ),
            execution=ExecutionInfo(
                started_at=utc_now_rfc3339(),
                ended_at=utc_now_rfc3339(),
                status=status,  # type: ignore[arg-type]
            ),
            result=ResultInfo(
                chunk_ids=chunk_ids or [],
                error=error,
            ),
            ext=merged_ext,
        )
        default_action_sink().append(record)
        log_structured(
            "info",
            (
                f"agent_action agent={state.agent} "
                f"action={action_name} "
                f"spiffe_id={state.spiffe_id}"
            ),
            service=os.getenv("TKEIR_SERVICE", "tkeir-agent"),
            correlation_id=state.correlation_id or "",
            action_id=record.action_id,
            actor=state.agent,
            agent=state.agent,
            action=action_name,
            action_kind=kind,
            spiffe_id=state.spiffe_id,
            run_id=state.run_id,
            user_space=state.user_space,
            status=status,
            **(
                {"tool": str(merged_ext["tool"])}
                if merged_ext.get("tool")
                else {}
            ),
        )
        return record
