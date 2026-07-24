"""Title: Agent runtime models (Phase B) — specs, runs, steps, grounded output.

No orchestration frameworks: these pydantic models are the source of truth
for YAML agents and filesystem run stores.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from thot.action.models import new_action_id, utc_now_rfc3339


class BudgetLimits(BaseModel):
    """Per-run consumable budgets."""

    llm_tokens: int = 20000
    tool_calls: int = 15
    wall_seconds: int = 300
    docs_written: int = 0


class StopCondition(BaseModel):
    """When the single-agent loop must halt."""

    max_steps: int = 12


class AgentSpec(BaseModel):
    """Loaded from ``tkeir/configs/agents/*.yaml``."""

    name: str
    version: int = 1
    role: str = ""
    system_prompt: str = ""
    model: str = "${LLM_MODEL}"
    tools: list[str] = Field(default_factory=list)
    budgets: BudgetLimits = Field(default_factory=BudgetLimits)
    stop: StopCondition = Field(default_factory=StopCondition)
    output_contract: str = "grounded_findings_v1"
    temperature: float = 0.1


class GroundedFinding(BaseModel):
    """One claim with mandatory provenance."""

    claim: str
    chunk_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class GroundedFindings(BaseModel):
    """Researcher output contract."""

    schema_: str = Field(default="grounded_findings_v1", alias="schema")
    goal: str = ""
    findings: list[GroundedFinding] = Field(default_factory=list)
    unfilled: list[str] = Field(default_factory=list)
    notes: str = ""

    model_config = {"populate_by_name": True}


class OkfEnrichmentFindingModel(BaseModel):
    """One ``okf_enrichment_v1`` finding (mirrors thot.okf.models)."""

    concept_id: str
    claim: str = ""
    enrichments: dict[str, Any] = Field(default_factory=dict)
    chunk_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class OkfEnrichmentResult(BaseModel):
    """OKF curator output contract."""

    schema_: str = Field(default="okf_enrichment_v1", alias="schema")
    findings: list[OkfEnrichmentFindingModel] = Field(default_factory=list)
    unfilled: list[str] = Field(default_factory=list)
    notes: str = ""

    model_config = {"populate_by_name": True}


class ToolCall(BaseModel):
    """Parsed tool invocation from the LLM."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class StepRecord(BaseModel):
    """One reason→act→observe step persisted under ``steps/NNN.json``."""

    step_index: int
    started_at: str = Field(default_factory=utc_now_rfc3339)
    ended_at: str = ""
    thought_excerpt: str = ""
    tool_call: ToolCall | None = None
    observation: dict[str, Any] | None = None
    final: GroundedFindings | None = None
    status: Literal[
        "ok", "parse_error", "blocked", "budget", "killed", "error"
    ] = "ok"
    error: str | None = None
    action_id: str = Field(default_factory=new_action_id)


class BudgetUsage(BaseModel):
    """Live counters for a run."""

    llm_tokens: int = 0
    tool_calls: int = 0
    wall_seconds: float = 0.0
    docs_written: int = 0


class RunSpec(BaseModel):
    """Inbound create-run request."""

    agent: str = "researcher"
    workflow: str | None = None
    goal: str
    params: dict[str, Any] = Field(default_factory=dict)
    template: str | None = None


class Handoff(BaseModel):
    """Explicit supervisor→worker (or worker→worker) handoff record."""

    handoff_id: str = Field(default_factory=new_action_id)
    from_agent: str
    to_agent: str
    reason: str = ""
    payload_summary: str = ""
    chunk_ids: list[str] = Field(default_factory=list)
    at: str = Field(default_factory=utc_now_rfc3339)


class WorkflowAgentStep(BaseModel):
    """One sequential agent phase in a workflow."""

    id: str = ""
    agent: str
    goal_template: str = "{goal}"
    tools: list[str] | None = None
    max_steps: int | None = None


class WorkflowComposeStep(BaseModel):
    """Final templated deliverable step."""

    id: str = "compose"
    template: str = "synthesis_note"
    topic_from: str = "goal"


class WorkflowStep(BaseModel):
    """Workflow step: agent, compose, or builtin (e.g. OKF scoped export)."""

    id: str = ""
    agent: str | None = None
    goal_template: str = "{goal}"
    tools: list[str] | None = None
    max_steps: int | None = None
    compose: WorkflowComposeStep | None = None
    builtin: str | None = None
    params_from: list[str] = Field(default_factory=list)
    output_key: str | None = None


class WorkflowSpec(BaseModel):
    """Loaded from ``tkeir/configs/workflows/*.yaml``."""

    name: str
    version: int = 1
    description: str = ""
    template: str | None = None
    budgets: BudgetLimits = Field(default_factory=BudgetLimits)
    steps: list[WorkflowStep] = Field(default_factory=list)
    external_tools: list[str] = Field(default_factory=list)


class RunState(BaseModel):
    """Persisted run manifest."""

    schema_: str = Field(default="tkeir.agent.run.v1", alias="schema")
    run_id: str = Field(default_factory=new_action_id)
    agent: str = "researcher"
    workflow: str | None = None
    goal: str = ""
    user_space: str = "dev@tkeir"
    spiffe_id: str | None = None
    correlation_id: str = ""
    status: Literal[
        "queued",
        "running",
        "succeeded",
        "failed",
        "cancelled",
        "blocked",
        "killed",
    ] = "queued"
    created_at: str = Field(default_factory=utc_now_rfc3339)
    updated_at: str = Field(default_factory=utc_now_rfc3339)
    started_at: str = ""
    ended_at: str = ""
    steps_completed: int = 0
    budgets: BudgetLimits = Field(default_factory=BudgetLimits)
    usage: BudgetUsage = Field(default_factory=BudgetUsage)
    result: GroundedFindings | None = None
    compose_result: dict[str, Any] | None = None
    handoffs: list[Handoff] = Field(default_factory=list)
    delegation_chain: list[str] = Field(default_factory=list)
    error: str | None = None
    cancel_requested: bool = False
    params: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}
