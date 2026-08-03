"""Title: Models

Governor domain models.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

KillScope = Literal[
    "all", "ingest", "index", "inference", "hmi-write", "agents"
]
PolicyResult = Literal["allow", "deny", "escalate"]


class KillSwitchState(BaseModel):
    """Per-scope kill-switch state.

    Example:
        >>> from thot.governor.models import KillSwitchState
        >>> KillSwitchState(active=True, reason="drill").active
        True
    """

    active: bool = False
    reason: str = ""
    activated_at: str = ""
    activated_by: str = ""


class RuntimeFlags(BaseModel):
    """Mutable runtime flags (kill switch per scope).

    Example:
        >>> from thot.governor.models import RuntimeFlags
        >>> RuntimeFlags.model_validate({"updated_at": "2026-01-01T00:00:00Z"})
        RuntimeFlags(schema_='tkeir.governor.flags.v1', updated_at='2026-01-01T00:00:00Z', scopes={})
    """

    schema_: str = Field(default="tkeir.governor.flags.v1", alias="schema")
    updated_at: str = ""
    scopes: dict[KillScope, KillSwitchState] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class BudgetSnapshot(BaseModel):
    """Budget consumption snapshot for one actor and unit.

    Example:
        >>> from thot.governor.models import BudgetSnapshot
        >>> BudgetSnapshot(
        ...     actor_id="demo", unit="docs", limit=100.0, consumed=10.0,
        ...     ratio=0.1, throttled=False, blocked=False,
        ... ).ratio
        0.1
    """

    actor_id: str
    unit: str
    limit: float
    consumed: float
    ratio: float
    throttled: bool
    blocked: bool


class ApprovalItem(BaseModel):
    """One pending or decided approval queue entry.

    Example:
        >>> from thot.governor.models import ApprovalItem
        >>> ApprovalItem(
        ...     approval_id="a1", correlation_id="b" * 32,
        ...     actor_id="u1", intent="ingest", reason="escalate",
        ...     created_at="2026-01-01T00:00:00Z",
        ... ).status
        'pending'
    """

    approval_id: str
    correlation_id: str
    actor_id: str
    intent: str
    reason: str
    created_at: str
    status: Literal["pending", "approved", "denied"] = "pending"


class PolicyDecision(BaseModel):
    """Outcome of a single governor evaluation.

    Example:
        >>> from thot.governor.models import PolicyDecision
        >>> PolicyDecision(result="allow", actor_id="svc").result
        'allow'
    """

    result: PolicyResult = "allow"
    rules_fired: list[str] = Field(default_factory=list)
    kill_scope: KillScope | None = None
    budget: BudgetSnapshot | None = None
    actor_id: str = "anonymous"
    intent: str = "search"
    message: str = ""


class KillRequest(BaseModel):
    """HTTP body to toggle a kill-switch scope.

    Example:
        >>> from thot.governor.models import KillRequest
        >>> KillRequest(scope="inference", active=True, reason="drill").scope
        'inference'
    """

    scope: KillScope
    active: bool = True
    reason: str = ""


class RollbackRequest(BaseModel):
    """HTTP body to request indexer rollback by run id.

    Example:
        >>> from thot.governor.models import RollbackRequest
        >>> RollbackRequest(run_id="run-1", reason="bad deploy").run_id
        'run-1'
    """

    run_id: str | None = None
    reason: str = ""


class ApprovalDecision(BaseModel):
    """Optional note when approving or denying an item.

    Example:
        >>> from thot.governor.models import ApprovalDecision
        >>> ApprovalDecision(note="looks good").note
        'looks good'
    """

    note: str = ""


class MintTokenRequest(BaseModel):
    """HTTP body to mint a constrained action token.

    Example:
        >>> from thot.governor.models import MintTokenRequest
        >>> MintTokenRequest(intent="search", ttl=60).intent
        'search'
    """

    intent: str = "search"
    audience: str = "tkeir-action"
    max_budget: float = 0.0
    ttl: int = 300
    constraints: dict[str, Any] = Field(default_factory=dict)


class RevokeTokenRequest(BaseModel):
    """HTTP body to revoke an action token.

    Example:
        >>> from thot.governor.models import RevokeTokenRequest
        >>> RevokeTokenRequest(jti="tok-1").jti
        'tok-1'
    """

    jti: str | None = None
    actor_id: str | None = None
    reason: str = ""
