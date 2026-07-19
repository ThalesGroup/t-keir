"""Governor domain models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

KillScope = Literal[
    "all", "ingest", "index", "inference", "hmi-write", "agents"
]
PolicyResult = Literal["allow", "deny", "escalate"]


class KillSwitchState(BaseModel):
    active: bool = False
    reason: str = ""
    activated_at: str = ""
    activated_by: str = ""


class RuntimeFlags(BaseModel):
    """Mutable runtime flags (kill switch per scope)."""

    schema_: str = Field(default="tkeir.governor.flags.v1", alias="schema")
    updated_at: str = ""
    scopes: dict[KillScope, KillSwitchState] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class BudgetSnapshot(BaseModel):
    actor_id: str
    unit: str
    limit: float
    consumed: float
    ratio: float
    throttled: bool
    blocked: bool


class ApprovalItem(BaseModel):
    approval_id: str
    correlation_id: str
    actor_id: str
    intent: str
    reason: str
    created_at: str
    status: Literal["pending", "approved", "denied"] = "pending"


class PolicyDecision(BaseModel):
    """Outcome of a single governor evaluation."""

    result: PolicyResult = "allow"
    rules_fired: list[str] = Field(default_factory=list)
    kill_scope: KillScope | None = None
    budget: BudgetSnapshot | None = None
    actor_id: str = "anonymous"
    intent: str = "search"
    message: str = ""


class KillRequest(BaseModel):
    scope: KillScope
    active: bool = True
    reason: str = ""


class RollbackRequest(BaseModel):
    run_id: str | None = None
    reason: str = ""


class ApprovalDecision(BaseModel):
    note: str = ""


class MintTokenRequest(BaseModel):
    intent: str = "search"
    audience: str = "tkeir-action"
    max_budget: float = 0.0
    ttl: int = 300
    constraints: dict[str, Any] = Field(default_factory=dict)


class RevokeTokenRequest(BaseModel):
    jti: str | None = None
    actor_id: str | None = None
    reason: str = ""
