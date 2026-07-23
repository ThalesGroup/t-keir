# Agents (`tkeir-agent`)

Agents are a **core T-KEIR feature**: tool-using research and **multi-agent
workflows** over the caller’s Vespa `user_space`, with ontology-driven template
compose and approval-gated publication.

The runtime is written **from scratch** (no LangChain / CrewAI / AutoGen). The
LLM is `UnifiedLLMWrapper` (Ollama / OpenAI / vLLM). Tools reuse the same MCP
**handlers library** as `tkeir-mcp` (`search`, `rag_query`, `ontology_query`,
`document_get`) plus optional outbound MCP tools.

**You do not need the MCP service running for agents.** `tkeir-mcp` is only for
**external** MCP clients. Agents call `McpHandlers` in-process against Vespa /
RAG — see [MCP — Who uses it](mcp.md#who-uses-it-external-vs-agents).

> Design: [ADR-0005](../adr/0005-agent-architecture.md),
> [ADR-0006](../adr/0006-kg-store.md) (templates / fused KG),
> [ADR-0007](../adr/0007-generated-content.md) (publish),
> [ADR-0008](../adr/0008-spire-agent-identity.md).  
> Related: [MCP](mcp.md), [Templates](templates.md),
> [Zero to Hero §4.4](../zero_to_hero.md#44-agents-on-osint-and-enterprise-demo-data-p0).

---

## Architecture

```text
POST /agent/runs  { agent | workflow, goal, params }
        │
        ▼
   RunStore  (.tkeir-agent/runs/{id}/)
        │
   ┌────┴────────────────────────────┐
   │ single agent          workflow  │
   │ AgentLoop             Orchestrator (sequential)
   │   reason → act →      │ research → analyze → compose
   │   observe → final     │ Handoff + blackboard
   └────┬──────────────────┴─────────┘
        │
   ToolRegistry ──► McpHandlers (Vespa RAG)
                 └► OutboundMcpClient (egress allow-list)
        │
   AgentGuard ──► kill / budgets / ActionRecords / SPIFFE
        │
   optional Publish ──► ApprovalQueue → AGENT_ROOT/publishes/
```

| Module | Role |
|--------|------|
| `service.py` | FastAPI app (`tkeir-agent`), create/poll/cancel/publish |
| `registry.py` | Load `configs/agents/*.yaml` → `AgentSpec` |
| `workflows.py` | Load `configs/workflows/*.yaml` → `WorkflowSpec` |
| `loop.py` | Single-agent reason→act→observe until final / budget / kill |
| `orchestrator.py` | Sequential multi-agent plan + compose step |
| `toolbox.py` | Allow-listed tool invoke + schema validation |
| `safety.py` | `<untrusted>` envelopes, injection / escalation heuristics |
| `guard.py` | Governor flags, budgets, ActionRecords, SPIFFE |
| `runs.py` | Filesystem run store (manifest, steps, blackboard, DLQ) |
| `publish.py` | Approval-gated staging of agent markdown |
| `spiffe.py` | Dev / workload SPIFFE id for `actor.spiffe_id` |
| `models.py` | Pydantic specs: agents, workflows, runs, findings |

---

## Quick start

```bash
# From repository root — agent service on :8092
make agent

# Single researcher
make agent-run GOAL="Summarize SITREP findings about Objective ALPHA" AGENT=researcher

# Multi-agent workflow (researcher → analyst → synthesis_note compose)
make workflow-run \
  GOAL="Produce an OSINT content brief on Objective ALPHA" \
  WORKFLOW=content_brief \
  TOPIC="Objective ALPHA"
```

Polling waits several minutes by default (`AGENT_POLL_ATTEMPTS` /
`WORKFLOW_POLL_ATTEMPTS`). If Make times out, the run may still finish:

```bash
curl -s http://localhost:8092/agent/runs/<run_id> \
  | jq '{status:.run.status, handoffs, compose_result}'
```

**Prerequisites:** Vespa indexed for the target `user_space`, RAG API reachable
by the in-process handlers (`MCP_RAG_URL` / default `:8090`), and a working LLM
(`PROVIDER` / `LLM_MODEL`, e.g. Ollama). The `tkeir-mcp` process is **not**
required.

---

## HTTP API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/agent/runs` | Start async run `{agent\|workflow, goal, params?}` |
| `GET` | `/agent/runs/{id}` | Manifest, steps, handoffs, compose_result, budgets |
| `POST` | `/agent/runs/{id}/cancel` | Request cancel |
| `POST` | `/agent/runs/{id}/publish` | Stage / approve publish of compose markdown |
| `GET` | `/agent/workflows` | List workflow names |
| `GET` | `/health` `/ready` `/metrics` | Ops |

**Create run body (single agent):**

```json
{
  "agent": "researcher",
  "goal": "What does the corpus say about Objective ALPHA?"
}
```

**Create run body (workflow):**

```json
{
  "workflow": "content_brief",
  "goal": "OSINT brief on Objective ALPHA",
  "params": { "topic": "Objective ALPHA" }
}
```

**Tenant:** `user_space` comes from Bearer JWT (Keycloak) or
`VESPA_USER_SPACE` / `dev@tkeir`. Tool arguments **cannot** override
`user_space`.

---

## Agent configs (`tkeir/configs/agents/`)

Each file is one role. Loaded by `load_agent_spec(name)`.

| Field | Meaning |
|-------|---------|
| `name` | Registry key (`researcher`, …) |
| `version` | Spec version integer |
| `role` | Short human label |
| `system_prompt` | Instructions + JSON reply contract |
| `model` | Usually `${LLM_MODEL}` (env-expanded) |
| `tools` | Allow-list of tool names (empty = no tools) |
| `budgets` | `llm_tokens`, `tool_calls`, `wall_seconds` |
| `stop.max_steps` | Max reason→act iterations |
| `output_contract` | Expected final JSON shape |
| `temperature` | LLM temperature |

### Shipped agents

| Agent | Tools | Output contract | Role |
|-------|-------|-----------------|------|
| **researcher** | `search`, `rag_query`, `ontology_query`, `document_get` | `grounded_findings_v1` | Corpus research; claims need `chunk_ids` |
| **analyst** | `search`, `ontology_query`, `document_get` | `grounded_findings_v1` | Ontology / KG-oriented analysis |
| **writer** | _(none)_ | `grounded_prose_v1` | Fill freeform template slots from KG context |
| **reviewer** | _(none)_ | `review_verdict_v1` | Accept/reject slots by provenance |

**Example — `researcher.yaml` (abridged):**

```yaml
name: researcher
version: 1
role: "Corpus researcher"
system_prompt: |
  You research the user's corpus. ...
  Allowed tools: search, rag_query, ontology_query, document_get.
model: ${LLM_MODEL}
tools:
  - search
  - rag_query
  - ontology_query
  - document_get
budgets:
  llm_tokens: 20000
  tool_calls: 15
  wall_seconds: 300
stop:
  max_steps: 12
output_contract: grounded_findings_v1
temperature: 0.1
```

Add a new agent by dropping another YAML in `configs/agents/` with a unique
`name` and restarting `tkeir-agent`.

---

## Workflow configs (`tkeir/configs/workflows/`)

Workflows are **sequential supervisor plans** (no parallel fan-out). Loaded by
`load_workflow(name)`.

| Field | Meaning |
|-------|---------|
| `name` | Registry key |
| `description` | Human summary |
| `template` | Default compose template (e.g. `synthesis_note`) |
| `budgets` | Shared caps for the whole workflow |
| `external_tools` | Extra outbound MCP tools merged into early steps |
| `steps[]` | Ordered agent phases and/or a final `compose` phase |

### Step shapes

**Agent step:**

```yaml
- id: research
  agent: researcher
  goal_template: "Research the corpus for: {goal}"
  tools:                    # optional override of agent YAML tools
    - search
    - rag_query
  max_steps: 8              # optional override of stop.max_steps
```

`goal_template` may use `{goal}` and any key from `params` (e.g. `{topic}`).

**Compose step:**

```yaml
- id: deliverable
  compose:
    template: synthesis_note
    topic_from: topic       # reads params.topic (fallback: goal)
```

Compose uses `thot.compose` over the tenant fused KG (`UserSpaceKG`) plus
findings / chunk ids accumulated on the blackboard. Writer/reviewer agents
ground freeform slots — see [Templates](templates.md).

### Shipped workflow: `content_brief`

```yaml
name: content_brief
version: 1
description: >
  researcher → analyst → ontology-driven template compose
template: synthesis_note
budgets:
  llm_tokens: 60000
  tool_calls: 40
  wall_seconds: 600
external_tools:
  - echo_cite
steps:
  - id: research
    agent: researcher
    goal_template: "Research the corpus for: {goal}"
    tools: [search, rag_query, ontology_query, document_get, echo_cite]
    max_steps: 8
  - id: analyze
    agent: analyst
    goal_template: "Analyze ontology / KG facts for: {goal}"
    tools: [search, ontology_query, document_get]
    max_steps: 6
  - id: deliverable
    compose:
      template: synthesis_note
      topic_from: topic
```

**Runtime behaviour (`Orchestrator`):**

1. Set status `running`, mint governor action token, emit `agent.plan`.
2. For each agent step: load `AgentSpec`, apply tool/max_steps overrides, run
   `AgentLoop`, record a `Handoff`, append findings to the blackboard.
3. For compose: build template from KG + blackboard → `compose_result` on the
   run (markdown + JSON with citations / unfilled slots).
4. Terminal status: `succeeded` / `failed` / `blocked` / `killed` / `cancelled`.

Add a workflow by creating `configs/workflows/<name>.yaml` and referencing
existing agent names.

---

## Single-agent loop contract

The model must reply with **exactly one** JSON fence (or bare JSON object):

**Tool call:**

```json
{"tool": "search", "arguments": {"query": "Objective ALPHA"}}
```

**Final (grounded findings):**

```json
{
  "final": true,
  "findings": [
    {
      "claim": "...",
      "chunk_ids": ["..."],
      "document_ids": [],
      "confidence": 0.8
    }
  ],
  "unfilled": [],
  "notes": ""
}
```

**Hard rules enforced by `AgentLoop` / `safety`:**

- Claims **without** `chunk_ids` or `document_ids` are dropped into `unfilled`
  (no uncited generation).
- Tools outside the agent allow-list → `PermissionError`.
- Tool / document payloads are wrapped in `<untrusted source="…">` before being
  fed back to the model; injection / escalation phrases are redacted or refused.
- Loop stops on: final, `max_steps`, budget (80% throttle / 100% block), kill
  switch, or cancel.

---

## Tools

### Internal (MCP handlers, in-process)

Same catalog as [MCP](mcp.md), executed via `ToolRegistry` → `McpHandlers`
inside `tkeir-agent` (not via HTTP to `:8093`).

| Tool | Purpose |
|------|---------|
| `search` | Hybrid Vespa retrieval |
| `rag_query` | Retrieval + optional answer generation |
| `ontology_query` | Merge parent `json_ld` for query hits; summarize triples |
| `document_get` | Fetch one parent document by id |

### External (outbound MCP)

Configured in `tkeir/configs/mcp-client.yaml` (egress allow-list). Demo tool:
`echo_cite`. Workflow `external_tools` can enable them on specific steps.
These call **other** MCP servers; they are unrelated to whether local
`tkeir-mcp` is up.

---

## Run store layout

Root: `AGENT_ROOT` (Make: `.tkeir-agent/`).

```text
.tkeir-agent/
  runs/{run_id}/
    run.manifest.json     # RunState
    blackboard.json       # append-only handoff / findings log
    steps/000.json …      # StepRecord per loop iteration
  jobs/{run_id}.json      # lightweight status index
  dlq/{run_id}.json       # crashed runs
  publishes/{run_id}/     # staged markdown (after publish)
```

---

## Governance & identity

| Control | Behaviour |
|---------|-----------|
| Kill switch | `make governor-kill SCOPE=agents ACTIVE=true` |
| Budgets | `llm_tokens`, `tool_calls`, `wall_seconds` — throttle @ 80%, block + ApprovalQueue @ 100% in `enforce` |
| ActionRecords | Every plan / step / tool / handoff (`actor.type=agent`, `actor.spiffe_id`) |
| SPIFFE | `SPIFFE_MODE=dev\|workload`, `SPIFFE_ENFORCE`; Compose `PROFILES=…,spire,agents` |
| Publish | Enforce mode requires ApprovalQueue (`/admin`); observe may auto-stage |

---

## HMI

Open [http://localhost:3000/agents](http://localhost:3000/agents) with
`AGENT_URL=http://localhost:8092`.

- Start `content_brief` (or list workflows), poll status / handoffs / compose
  preview.
- **Publish** stages markdown under `AGENT_ROOT/publishes/{run_id}/` with
  `origin=agent-generated`.

---

## Environment

| Variable | Default / notes |
|----------|-----------------|
| `AGENT_ROOT` | Run store root (Make sets `.tkeir-agent`) |
| `AGENT_HOST` / `AGENT_PORT` | `0.0.0.0` / `8092` |
| `PROVIDER` / `LLM_MODEL` | Same stack as RAG |
| `MCP_RAG_URL` | RAG base URL for tool handlers |
| `VESPA_USER_SPACE` | Auth-off tenant |
| `GOVERNOR_MODE` | `observe` / `enforce` |
| `SPIFFE_*` | See [SPIRE](../deployment/spire.md) |
| `AGENT_PUBLISH_OBSERVE_AUTO` | Auto-publish in observe (`1` default) |

Compose profile: `PROFILES=…,agents` (image `tkeir-agent`).

---

## Extending

1. **New role** — add `configs/agents/my_agent.yaml`, restart service, call
   `POST /agent/runs` with `"agent": "my_agent"`.
2. **New workflow** — add `configs/workflows/my_flow.yaml` chaining agents and
   optional `compose`, then `"workflow": "my_flow"`.
3. **New tool** — register in MCP catalog / outbound client, then add the name
   to an agent’s `tools` or a workflow step `tools` list.
4. **New template** — see [Templates](templates.md); reference it from a
   workflow `compose.template`.
