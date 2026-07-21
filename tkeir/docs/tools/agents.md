# Agents (tkeir-agent)

Agents are a **core T-KEIR feature**: tool-using research and multi-agent
workflows over the caller's Vespa `user_space`, with ontology-driven templates
and approval-gated publication. The runtime is written from scratch (no
LangChain / CrewAI / etc.) on `UnifiedLLMWrapper`.

> Implementation phases: single-agent (B), templates (C), multi-agent + outbound
> MCP (D), HMI monitor + publish (E). See ADR-0005 / ADR-0007.

## Quick start

```bash
make agent
# single agent:
make agent-run GOAL="What does the corpus say about X?"
# multi-agent workflow (researcher → analyst → template compose):
make workflow-run GOAL="Profile Acme" WORKFLOW=content_brief TOPIC=Acme
```

API:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/agent/runs` | Start async run `{agent\|workflow, goal, params?}` |
| `GET` | `/agent/runs/{id}` | State, steps, handoffs, compose_result, budgets |
| `POST` | `/agent/runs/{id}/cancel` | Request cancel |
| `GET` | `/agent/workflows` | List workflows |
| `GET` | `/health` `/ready` `/metrics` | Ops |

Base agents: `researcher`, `analyst`, `writer`, `reviewer` under
`tkeir/configs/agents/`.

Workflow: `tkeir/configs/workflows/content_brief.yaml`.

## Governance

- Kill-switch scope **`agents`**: `make governor-kill SCOPE=agents ACTIVE=true`
- Budgets per run: `llm_tokens`, `tool_calls`, `wall_seconds` (80% throttle /
  100% block + ApprovalQueue in `enforce`)
- Every plan / step / tool / handoff → `ActionRecord` (`actor.type=agent`,
  **`actor.spiffe_id`** set — [ADR-0008](../adr/0008-spire-agent-identity.md))
- Tenant: `user_space` from Bearer / `VESPA_USER_SPACE`; tool args cannot override
- SPIFFE: `SPIFFE_MODE=dev|workload`, `SPIFFE_ENFORCE` with governor enforce;
  Compose `PROFILES=…,spire,agents` — see [SPIRE / SPIFFE](../deployment/spire.md)

## Outbound MCP (Phase D)

External tools go through `thot.mcp.client.OutboundMcpClient` with an egress
allow-list (`tkeir/configs/mcp-client.yaml`). Demo tool: `echo_cite`. All
external outputs are wrapped in `<untrusted>` envelopes.

## Loop contract

The model must reply with one JSON fence:

```json
{"tool": "search", "arguments": {"query": "..."}}
```

or

```json
{"final": true, "findings": [{"claim": "...", "chunk_ids": ["..."]}], "unfilled": []}
```

Claims without `chunk_ids` / `document_ids` are dropped into `unfilled`
(no uncited generation).

## HMI run monitor (Phase E)

Open [http://localhost:3000/agents](http://localhost:3000/agents) (with
`tkeir-hmi` running and `AGENT_URL` pointing at `:8092`).

- Start `content_brief` (or another workflow), poll status / handoffs / compose
  preview.
- **Publish** stages markdown under `AGENT_ROOT/publishes/{run_id}/` with
  `origin=agent-generated`. In enforce mode the governor ApprovalQueue must
  approve first (`/admin`).

```bash
# server-side proxy target for the HMI
export AGENT_URL=http://localhost:8092
```

## Layout

```text
tkeir/thot/agent/
  models.py registry.py workflows.py toolbox.py safety.py
  guard.py loop.py orchestrator.py runs.py publish.py service.py
tkeir/thot/mcp/client.py   # outbound MCP + egress
```

See also [MCP server](mcp.md), [Templates](templates.md), ADR-0005 / ADR-0007.
