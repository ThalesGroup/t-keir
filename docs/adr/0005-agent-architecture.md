# ADR-0005 — Agent architecture (from-scratch runtime)

- **Status:** Accepted (Phase B–D)
- **Date:** 2026-07-19
- **Deciders:** T-KEIR maintainers
- **Tags:** agents, mcp, governance

## Context

T-KEIR needs tool-using agents and multi-agent workflows without adopting an
orchestration framework (LangChain, CrewAI, AutoGen, etc.). LLM access must
remain provider-agnostic via `UnifiedLLMWrapper`, and every step must emit
`ActionRecord`s under the governor (kill switch scope `agents`, budgets,
approvals).

## Decision

1. Implement the agent loop, toolbox, guard, run store, and orchestrator in
   `tkeir/thot/agent/` from scratch.
2. Expose T-KEIR retrieval as an MCP *server* (`thot/mcp/`) with the official
   MCP SDK isolated behind `transport.py`.
3. Call external MCP tools only through `thot/mcp/client.py` with an egress
   allow-list (`configs/mcp-client.yaml`); wrap all tool/document content in
   `<untrusted>` envelopes.
4. Ship base agents as YAML (`configs/agents/`) and workflows as YAML
   (`configs/workflows/`); sequential orchestration first.
5. Service: `tkeir-agent` on `:8092`.
6. **Workload identity:** every agent run carries a SPIFFE ID
   (`spiffe://{trust}/agent/{name}`) on `RunState` and
   `ActionRecord.actor.spiffe_id` ([ADR-0008](0008-spire-agent-identity.md)).
   Governor enforce mode denies agent steps without an allow-listed ID.

## Consequences

- No framework lock-in; CI docstring/example gates apply to new modules.
- Multi-agent fan-out and streaming UI remain future work (Phase E surfaces a
  minimal poll monitor only).
- See [Agents](../tools/agents.md), [MCP](../tools/mcp.md),
  [SPIRE / SPIFFE](../deployment/spire.md).
