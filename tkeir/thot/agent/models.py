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
    """Per-run consumable budgets.

    Example:
        >>> from thot.agent.models import BudgetLimits
        >>> BudgetLimits(tool_calls=10).tool_calls
        10
    """

    llm_tokens: int = 20000
    tool_calls: int = 15
    wall_seconds: int = 300
    docs_written: int = 0


class StopCondition(BaseModel):
    """When the single-agent loop must halt.

    Example:
        >>> from thot.agent.models import StopCondition
        >>> StopCondition(max_steps=5).max_steps
        5
    """

    max_steps: int = 12


class AgentSpec(BaseModel):
    """Loaded from ``tkeir/configs/agents/*.yaml`` or ``datasets/*/agents/``.

    Persona ``*_prompt`` agents may set wiki generation fields used by the
    ``wiki_upsert`` builtin (HMI passes ``prompt_name`` / ``wiki_agent``).

    Prefer constructing an identified :class:`~thot.agent.agent.Agent` via
    ``Agent.load(name)`` rather than using the raw spec alone.

    Example:
        >>> from thot.agent.models import AgentSpec
        >>> AgentSpec(name="researcher", tools=["search"]).name
        'researcher'
    """

    name: str
    version: int = 1
    role: str = ""
    system_prompt: str = ""
    model: str = "${LLM_MODEL}"
    tools: list[str] = Field(default_factory=list)
    budgets: BudgetLimits = Field(default_factory=BudgetLimits)
    stop: StopCondition = Field(default_factory=StopCondition)
    output_contract: str = "grounded_findings_v1"
    temperature: float = 0.0
    # Tools whose successful observation (``ok: true``) ends the agent phase
    # without waiting for a separate ``final: true`` model message.
    terminal_tools: list[str] = Field(default_factory=list)
    # --- OKF wiki generation (persona prompt agents) ---
    wiki_structured_facts_seed: str = Field(
        default="",
        description=(
            "Optional markdown section injected into the OKF wiki.md seed "
            "(e.g. Structured facts checklist). Empty = Google OKF core only "
            "(Answer / Evidence / Sources)."
        ),
    )
    wiki_merge_system_prompt: str = Field(
        default="",
        description=(
            "System prompt for the OKF wiki single-pass fold LLM call. "
            "Empty = generic OKF merge system (no form-specific checklist)."
        ),
    )
    wiki_information_priority_keys: list[str] = Field(
        default_factory=list,
        description=(
            "Optional priority substrings for compact_information_for_prompt "
            "(persona/use-case specific; empty = preserve Information line order)."
        ),
    )


class GroundedFinding(BaseModel):
    """One claim with mandatory provenance.

    Example:
        >>> from thot.agent.models import GroundedFinding
        >>> GroundedFinding(claim="Acme launched Widget", chunk_ids=["c1"]).claim
        'Acme launched Widget'
    """

    claim: str
    chunk_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class GroundedFindings(BaseModel):
    """Researcher output contract.

    Example:
        >>> from thot.agent.models import GroundedFinding, GroundedFindings
        >>> out = GroundedFindings(
        ...     goal="summarize",
        ...     findings=[GroundedFinding(claim="fact")],
        ... )
        >>> out.schema_
        'grounded_findings_v1'
    """

    schema_: str = Field(default="grounded_findings_v1", alias="schema")
    goal: str = ""
    findings: list[GroundedFinding] = Field(default_factory=list)
    unfilled: list[str] = Field(default_factory=list)
    notes: str = ""

    model_config = {"populate_by_name": True}


class OkfEnrichmentFindingModel(BaseModel):
    """One ``okf_enrichment_v1`` finding (mirrors thot.okf.models).

    Example:
        >>> from thot.agent.models import OkfEnrichmentFindingModel
        >>> OkfEnrichmentFindingModel(concept_id="doc-1", claim="enriched").concept_id
        'doc-1'
    """

    concept_id: str
    claim: str = ""
    enrichments: dict[str, Any] = Field(default_factory=dict)
    chunk_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class OkfEnrichmentResult(BaseModel):
    """OKF curator output contract.

    Example:
        >>> from thot.agent.models import OkfEnrichmentResult
        >>> OkfEnrichmentResult(schema="okf_enrichment_v1").schema_
        'okf_enrichment_v1'
    """

    schema_: str = Field(default="okf_enrichment_v1", alias="schema")
    findings: list[OkfEnrichmentFindingModel] = Field(default_factory=list)
    unfilled: list[str] = Field(default_factory=list)
    notes: str = ""

    model_config = {"populate_by_name": True}


class ToolCall(BaseModel):
    """Parsed tool invocation from the LLM.

    Example:
        >>> from thot.agent.models import ToolCall
        >>> ToolCall(name="search", arguments={"query": "q"}).name
        'search'
    """

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class StepRecord(BaseModel):
    """One reason→act→observe step persisted under ``steps/NNN.json``.

    Example:
        >>> from thot.agent.models import StepRecord
        >>> StepRecord(step_index=0).step_index
        0
    """

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
    """Live counters for a run.

    Example:
        >>> from thot.agent.models import BudgetUsage
        >>> BudgetUsage(tool_calls=3).tool_calls
        3
    """

    llm_tokens: int = 0
    tool_calls: int = 0
    wall_seconds: float = 0.0
    docs_written: int = 0


class RunSpec(BaseModel):
    """Inbound create-run request.

    Example:
        >>> from thot.agent.models import RunSpec
        >>> RunSpec(goal="analyze quarterly report").goal
        'analyze quarterly report'
    """

    agent: str = "researcher"
    workflow: str | None = None
    goal: str
    params: dict[str, Any] = Field(default_factory=dict)
    template: str | None = None


class Handoff(BaseModel):
    """Explicit supervisor→worker (or worker→worker) handoff record.

    Carries decision/memory context between agents. Index/RAG provenance
    stays on findings or tool observations — not on the handoff itself.

    Example:
        >>> from thot.agent.models import Handoff
        >>> Handoff(from_agent="supervisor", to_agent="researcher").to_agent
        'researcher'
    """

    handoff_id: str = Field(default_factory=new_action_id)
    from_agent: str
    to_agent: str
    reason: str = ""
    payload_summary: str = ""
    at: str = Field(default_factory=utc_now_rfc3339)


class WorkflowAgentStep(BaseModel):
    """One sequential agent phase in a workflow.

    Example:
        >>> from thot.agent.models import WorkflowAgentStep
        >>> WorkflowAgentStep(agent="researcher").agent
        'researcher'
    """

    id: str = ""
    agent: str
    goal_template: str = "{goal}"
    tools: list[str] | None = None
    max_steps: int | None = None


class WorkflowComposeStep(BaseModel):
    """Final templated deliverable step.

    Example:
        >>> from thot.agent.models import WorkflowComposeStep
        >>> WorkflowComposeStep(template="synthesis_note").template
        'synthesis_note'
    """

    id: str = "compose"
    template: str = "synthesis_note"
    topic_from: str = "goal"


class WorkflowStep(BaseModel):
    """Workflow step: agent, compose, or builtin (e.g. OKF scoped export).

    Example:
        >>> from thot.agent.models import WorkflowStep
        >>> WorkflowStep(agent="researcher", id="research").agent
        'researcher'
    """

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
    """Loaded from ``tkeir/configs/workflows/*.yaml`` or ``datasets/*/workflows/``.

    Example:
        >>> from thot.agent.models import WorkflowSpec
        >>> WorkflowSpec(name="content_brief").name
        'content_brief'
    """

    name: str
    version: int = 1
    description: str = ""
    template: str | None = None
    budgets: BudgetLimits = Field(default_factory=BudgetLimits)
    steps: list[WorkflowStep] = Field(default_factory=list)
    external_tools: list[str] = Field(default_factory=list)


class RunState(BaseModel):
    """Persisted run manifest.

    Example:
        >>> from thot.agent.models import RunState
        >>> RunState(goal="investigate", user_space="dev@tkeir").status
        'queued'
    """

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
