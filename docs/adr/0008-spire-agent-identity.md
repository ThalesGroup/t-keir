# ADR-0008 — SPIRE / SPIFFE for agent identity and mastering

- **Status:** Accepted
- **Date:** 2026-07-21
- **Deciders:** T-KEIR maintainers
- **Tags:** identity, spire, spiffe, agents, governor
- **Supersedes:** [ADR-0004](0004-defer-spire.md)

## Context

ADR-0004 deferred SPIRE to late production so P0–P2 development would not
depend on a node agent and trust domain. That decision conflicts with
**agent mastering**: tool-using agents (`tkeir-agent`) emit ActionRecords,
consume budgets, and honour the governor kill switch scope `agents`, yet
`ActorInfo.spiffe_id` was always `null`. Human tenant scoping
(`user_space` from Keycloak) alone cannot attest *which workload* ran the
agent loop when multiple agent pods/services share a realm.

[Identity of Action](../regularity-component/action-identiy.md) and
[Mastering of Action](../regularity-component/action-mastering.md) require
machine actors to be attributable. Agents are the first workload class
where SPIFFE is mandatory for enforce-mode mastering.

## Decision

1. **Adopt SPIRE** for the Compose profile `spire` and for P3+ when the
   `agents` profile (or Helm agent workload) is enabled.
2. **Trust domain** default: `tkeir.local` (`SPIFFE_TRUST_DOMAIN`).
3. **Agent SPIFFE ID shape:** `spiffe://{trust}/agent/{agent_name}`
   (sanitized). Allow-list via `SPIFFE_AGENT_ID_PREFIX` (comma-separated).
4. **Resolution** (`thot.agent.spiffe`):
   - `SPIFFE_MODE=off` — no ID (P0 without agents).
   - `SPIFFE_MODE=dev` (default) — synthesize ID without Workload API.
   - `SPIFFE_MODE=workload` — Workload API socket / `SPIFFE_ID` /
     `SPIFFE_ID_FILE`.
5. **Enforcement:** `SPIFFE_ENFORCE=true`, or governor `enforce` when
   SPIFFE mode is not `off`. Missing/disallowed IDs → deny run/step and
   emit blocked ActionRecords with `actor.spiffe_id` when known.
6. Every agent ActionRecord sets `actor.type=agent`, `actor.id=user_space`,
   and `actor.spiffe_id=<workload>`.
7. Non-agent services (RAG, ingest, indexer) remain JWT + correlation
   based until a later workstream extends SPIFFE to the full mesh.

## Consequences

- ADR-0004 is **superseded** (historical deferral for pre-agent phases).
- `deploy/spire/` + Compose `spire` profile land; installer reports SPIRE
  as optional capability to **install/reuse**, not skip.
- P0 RAG-only path unchanged (`SPIFFE_MODE` unused).
- Optional Python extra `spiffe` for Workload API clients.

## Related

- [ADR-0001](0001-platform-architecture.md)
- [ADR-0005](0005-agent-architecture.md)
- [SPIRE / SPIFFE](../deployment/spire.md)
- [Agents](../tools/agents.md)
