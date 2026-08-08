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

> Related: [MCP](mcp.md), [Templates](templates.md),
> [Zero to Hero §4.4](../zero_to_hero.md#44-agents-on-osint-and-enterprise-demo-data-p0).

---

## Architecture

```text
POST /agent/runs { agent | workflow, goal, params }
        │
        ▼
   RunStore (workspace/agent/runs/{id}/)
        │
   ┌────┴──────────────────────────────────────────┐
   │ single agent                 workflow         │
   │ LLMAgent → AgentLoop         Orchestrator     │
   │   reason → act →             │ agent steps → AgentLoop
   │   observe → final            │ wiki_* → WikiGeneratorWorkflow
   │                              │ compose / builtins
   └────┬─────────────────────────┴────────────────┘
        │
   ToolRegistry ──► McpHandlers (Vespa RAG)
                 └► OutboundMcpClient (egress allow-list)
        │
   AgentGuard (BaseAgentGuard) ──► kill / budgets / ActionRecords / SPIFFE
        │
   optional Publish ──► ApprovalQueue → AGENT_ROOT/publishes/
```

**Layers (keep wiki out of the general agent):**

| Layer | Types | Responsibility |
|-------|--------|----------------|
| Engine-agnostic | `BaseAgent`, `DecisionEngine`, `BaseAgentGuard` | Contracts only — no T-KEIR domain |
| General LLM | `LLMAgent` | ReAct via `AgentLoop`; tools + goal; **no** OKF/wiki imports |
| Domain | `WikiGeneratorWorkflow` | Match/create wiki, upsert / iterative fold |
| HTTP | `thot.tools.agent` | Hosts `AgentSet`; single-agent runs use `LLMAgent` |

| Module | Role |
|--------|------|
| **`thot.agent.base`** | Engine-agnostic `BaseAgent` / `DecisionEngine` / `BaseAgentGuard` |
| **`thot.agent.llm_agent`** | General-purpose `LLMAgent` (ReAct via `AgentLoop`, no wiki coupling) |
| **`thot.agent.agent`** | Library :class:`Agent` / :class:`AgentSet` (identified YAML roles) |
| `thot.agent.registry` | Load `configs/agents/*.yaml` + `datasets/*/agents/` → `AgentSpec` |
| `thot.agent.workflows` | YAML workflow loader + domain pipelines (`WikiGeneratorWorkflow`) |
| `thot.agent.loop` | Single-agent reason→act→observe until final / budget / kill |
| `thot.agent.orchestrator` | Sequential multi-agent plan + compose; wiki builtins delegate to `WikiGeneratorWorkflow` |
| `thot.agent.toolbox` | Allow-listed tool invoke + schema validation |
| `thot.agent.safety` | `<untrusted>` envelopes, injection / escalation heuristics |
| `thot.agent.guard` | Governor flags, budgets, ActionRecords, SPIFFE (`BaseAgentGuard`) |
| `thot.agent.runs` | Filesystem run store (manifest, steps, blackboard, DLQ) |
| `thot.agent.publish` | Approval-gated staging of agent markdown |
| **`thot.tools.agent`** | FastAPI HTTP tool (`tkeir-agent` :8092) hosting an `AgentSet` |
| `spiffe.py` | Dev / workload SPIFFE id for `actor.spiffe_id` |
| `models.py` | Pydantic specs: agents, workflows, runs, findings |

---

## Quick start

```bash
# From repository root — agent HTTP tool on :8092
make agent
# equivalent: python -m thot.tools.agent
# optional: --config-dir DIR (repeatable), --agents name1,name2

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
| `GET` | `/agent/agents` | Catalog (`?wiki=true` → wiki-capable `*_prompt`) |
| `GET` | `/agent/agents/{name}` | One catalog entry |
| `GET` | `/agent/templates` | Compose answer/report templates (`otan_sitrep`, …) |
| `GET` | `/agent/workflows` | List workflow names |
| `GET` | `/health` `/ready` `/metrics` | Ops |

**Preferred RAG → wiki → answer run:**

```json
{
  "workflow": "rag_with_wiki",
  "goal": "Gulf of Aden SITREP",
  "params": {
    "query": "Gulf of Aden SITREP",
    "use_wiki": true,
    "wiki_agent": "moc_watch_prompt",
    "answer_template": "otan_sitrep",
    "search_mode": "both",
    "stop_at_wiki_extract": false
  }
}
```

Set ``stop_at_wiki_extract: true`` to end after ``wiki_upsert`` (no
``answer_generate``). The same flag on ``POST /rag/query`` skips in-process
answer generation when ``use_wiki`` is set.

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

## Agent configs (`tkeir/configs/agents/` + `datasets/*/agents/`)

Each file is one role. Loaded by `load_agent_spec(name)` from core configs
and dataset packs (OSINT personas live under `datasets/osint/agents/`).

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

### Shipped agents (core — `tkeir/configs/agents/`)

| Agent | Tools | Output contract | Role |
|-------|-------|-----------------|------|
| **researcher** | `search`, `rag_query`, `ontology_query`, `document_get`, wiki list/get | `grounded_findings_v1` | Dual-index research (`search_mode=both`); claims need `chunk_ids` |
| **analyst** | `search`, `ontology_query`, `document_get` | `grounded_findings_v1` | Ontology / KG-oriented analysis |
| **writer** | _(none)_ | `grounded_prose_v1` | Fill freeform template slots from KG context |
| **reviewer** | _(none)_ | `grounded_findings_v1` | Accept/reject findings or slots by provenance |
| **okf_curator** | search/rag/ontology/`okf_bundle_get` | `okf_enrichment_v1` | Enrich OKF concepts |

### OSINT pack (`datasets/osint/agents/`)

| Agent | Role |
|-------|------|
| **`<persona>_{analyser,reviewer,writer}`** | RED HORIZON personas (j2_analyst, moc_watch, j2x_humint, ctf_commander, admin) |
| **`<persona>_prompt`** | OKF wiki seed + merge system for `wiki_upsert` (not a tool-loop agent) |
| **`wiki_writer`** | Answer-first OKF LLMWiki writer used by `otan_c2_brief` |

### Shipped workflows (core — `tkeir/configs/workflows/`)

| Workflow | Pipeline | Deliverable |
|----------|----------|-------------|
| **content_brief** | researcher → analyst → compose | `synthesis_note` |
| **okf_wiki_brief** | scoped OKF → okf_curator → compose | bundle + `synthesis_note` |
| **rag_with_wiki** | search_chunks → wiki_upsert → answer_generate | compose template (e.g. `otan_sitrep`) |

### OSINT pack (`datasets/osint/workflows/`)

| Workflow | Pipeline | Deliverable |
|----------|----------|-------------|
| **persona_*** | analyse → review → write → OTAN compose | INTSUM / SITREP / SPOTREP / Commander's Brief |
| **otan_c2_brief** | scoped OKF → researcher → reviewer → wiki_writer → OTAN compose | OTAN form + LLMWiki |
| **llm_wiki** | `wiki_upsert` (persona `*_prompt`; match via `index.md`) | detailed `wiki.md` |

**OTAN C2 params** (HMI Agents page or API):

```json
{
  "workflow": "otan_c2_brief",
  "goal": "Tell me everything about MT RED SEA EAGLE.",
  "params": {
    "topic": "MT RED SEA EAGLE",
    "report_form": "intsum",
    "use_existing_wiki": "true"
  }
}
```

`report_form`: `intsum` (J2) · `sitrep` (MOC) · `spotrep` (HUMINT) · `commander_brief` (CTF).

Form → compose template maps and writer slot hints are **usecase config**, not
hardcoded in the orchestrator:

- [`datasets/osint/agent_orchestrator.yaml`](../../datasets/osint/agent_orchestrator.yaml)
- [`datasets/enterprise/agent_orchestrator.yaml`](../../datasets/enterprise/agent_orchestrator.yaml)

Select with `params.usecase` / `params.dataset`, or env `TKEIR_AGENT_USECASE`
(also `TKEIR_DATASET` / `TKEIR_BUSINESS_ONTOLOGY_DATASET`). Override path:
`TKEIR_AGENT_ORCHESTRATOR_CONFIG`.

The same usecase also **prefers** that pack when agent/workflow YAML stems
collide across packs (e.g. `wiki_writer`, `llm_wiki`):
`datasets/<usecase>/agents|workflows` is searched before other packs.

**Reporter Phase 3** passes the edited Phase-2 LLM Wiki as the report base:

```json
{
  "workflow": "persona_j2_analyst",
  "goal": "Tell me everything about MT RED SEA EAGLE.",
  "params": {
    "topic": "MT RED SEA EAGLE",
    "report_form": "intsum",
    "use_existing_wiki": true,
    "bundle_id": "<okf-bundle-id>",
    "wiki_markdown": "---\\ntype: Wiki\\n..."
  }
}
```

Agents extract findings from that wiki (and `okf_bundle_get`), then reshape
claims for the OTAN compose template. Without `wiki_markdown`, optional
`use_existing_wiki` can still seed from `wiki/*.md` in My files / the bundle.

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

## Workflow configs (`tkeir/configs/workflows/` + `datasets/*/workflows/`)

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
  tools: # optional override of agent YAML tools
    - search
    - rag_query
  max_steps: 8 # optional override of stop.max_steps
```

`goal_template` may use `{goal}` and any key from `params` (e.g. `{topic}`).

**Compose step:**

```yaml
- id: deliverable
  compose:
    template: synthesis_note
    topic_from: topic # reads params.topic (fallback: goal)
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

Root: ``AGENT_ROOT`` (Make default: ``workspace/agent/``; override with
``AGENT_ROOT=…``). Legacy ``.tkeir-agent/`` at the repo root is no longer the
default.

```text
workspace/agent/
  runs/{run_id}/
    run.manifest.json # RunState
    blackboard.json # append-only handoff / findings log
    steps/000.json … # StepRecord per loop iteration
  jobs/{run_id}.json # lightweight status index
  dlq/{run_id}.json # crashed runs
  publishes/{run_id}/ # staged markdown (after publish)
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
| `AGENT_ROOT` | Run store root (Make sets `workspace/agent`) |
| `AGENT_HOST` / `AGENT_PORT` | `0.0.0.0` / `8092` |
| `AGENT_URL` | `http://localhost:8092` (HMI / Make) |
| `TKEIR_AGENT_CONFIG_DIRS` | Extra agent YAML roots (`os.pathsep`-separated) |
| `TKEIR_AGENT_NAMES` | Optional comma allow-list of agent stems for this process |
| `WIKI_MATCH_THRESHOLD` | Jaccard floor for wiki reuse (default `0.15`) |
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
5. **Library (in-process)** — prefer `LLMAgent` for goal+tools loops; keep
   wiki/OKF in `WikiGeneratorWorkflow` (or a new module under
   `thot.agent.workflows`), not inside `LLMAgent` / `AgentLoop`.

```python
from thot.agent import LLMAgent, WikiGeneratorWorkflow
from thot.agent.guard import AgentGuard
from thot.agent.runs import RunStore

# General ReAct agent (HTTP single-agent path uses the same type)
agent = LLMAgent(store=store, guard=guard, llm=llm, spec=spec)
await agent.run(state, identity_context=state.spiffe_id, state=state, spec=spec)

# Domain wiki upsert (orchestrator builtins call this)
wiki = WikiGeneratorWorkflow(store=store, guard=guard, llm=llm)
await wiki.run_upsert(state)
```
