# Architecture decision log

Developer-oriented summaries of ADRs under [`../adr/`](../adr/index.md).
Status, dates, and decisions are taken from each ADR file header / Decision
section.

## 0001 — Platform operations architecture

**Status**: Accepted | **Date**: 2026-07-17 | **Tags**: deployment, iam, audit, profiles

### Problem
Progressive install (local → Compose → Kubernetes) with attributable actions
and auditable chains is required without forking P0.

### Decision
1. Profiles P0–P4 are value presets, not forked trees.
2. Layout under `deploy/` and Python packages under `thot/{action,governor,audit,ingest}/`.
3. Keycloak realm `tkeir` for identity; agent SPIFFE via ADR-0008.
4. ActionRecord v1 + hot PostgreSQL + WORM object lock.
5. Inference via existing `UnifiedLLMWrapper` env contract.
6. Cilium on Linux for P3; supply-chain pins in `versions.lock.yaml`.
7. Governor `observe` in P1/P2, `enforce` in P3/P4.

### Impact on developers
- Prefer `make compose-up PROFILES=…` and existing CLIs; do not rename entry points.
- Read [Deployment](../deployment/index.md) for profile matrices.

### Related
- [ADR-0001](../adr/0001-platform-architecture.md)

## 0002 — Ingest supersede and rollback

**Status**: Accepted (Phase 3) | **Tags**: ingest, rollback

### Problem
Idempotent ingest needs a path when content changes under the same logical
document or a bad index must be rolled back.

### Decision
1. Idempotency key `(doc_id, pipeline_config_sha256, embedder.sha256)`.
2. Supersede and rollback hooks documented for operators (`make rollback-index`).

### Impact on developers
- Re-ingest with unchanged digests is a noop; change content or config to supersede.
- See [Ingestion](../deployment/ingest.md).

### Related
- [ADR-0002](../adr/0002-ingest-supersede.md)

## 0003 — Two-tier audit store + WORM

**Status**: Accepted (Phase 4) | **Tags**: audit, worm

### Problem
Hash-chained ActionRecords must be queryable quickly while retaining immutable
archives.

### Decision
1. Hot tier: append-only PostgreSQL + hash chain.
2. Compliance tier: S3/MinIO object lock (WORM).
3. `tkeir-audit verify` / archive / forget tooling.

### Impact on developers
- Emit ActionRecords; do not UPDATE/DELETE hot rows.
- See [Audit store](../deployment/audit.md).

### Related
- [ADR-0003](../adr/0003-audit-store-worm.md)

## 0004 — Defer SPIRE / SPIFFE (historical)

**Status**: Superseded by ADR-0008 | **Date**: 2026-07-17 | **Tags**: identity, spire, spiffe, deployment

### Problem
SPIRE operational overhead was judged too high for early phases.

### Decision
(Historical) Do not install SPIRE in P0–P2; leave `spiffe_id` null by default.

### Impact on developers
- Follow **ADR-0008** for agent workloads; this ADR is retained for history only.

### Related
- [ADR-0004](../adr/0004-defer-spire.md) · [ADR-0008](../adr/0008-spire-agent-identity.md)

## 0005 — Agent architecture

**Status**: Accepted (Phase B–D) | **Date**: 2026-07-19 | **Tags**: agents, mcp, governance

### Problem
Tool-using agents are needed without adopting an orchestration framework.

### Decision
1. From-scratch loop in `thot/agent/`.
2. MCP server in `thot/mcp/`; outbound tools via allow-listed client.
3. YAML agents/workflows; service `tkeir-agent` on `:8092`.
4. SPIFFE ID on runs / ActionRecords (ADR-0008).

### Impact on developers
- Use `make agent` / `POST /agent/runs`; honour kill scope `agents`.
- See [Agents](../tools/agents.md).

### Related
- [ADR-0005](../adr/0005-agent-architecture.md)

## 0006 — Per-tenant fused KG store

**Status**: Accepted (Phase C) | **Date**: 2026-07-19 | **Tags**: ontology, kg, sparql, vespa

### Problem
Agents need a fused per-`user_space` RDF view without a separate vector store.

### Decision
Fuse document ontologies per tenant for SPARQL / agent tools; keep Vespa as
primary retrieval store.

### Impact on developers
- Document ontology JSON-LD on Vespa parents; derive-from reference ontologies
  when configured ([Document ontology](../tools/document_ontology.md)).

### Related
- [ADR-0006](../adr/0006-kg-store.md)

## 0007 — Agent-generated content publication

**Status**: Accepted (Phase E) | **Date**: 2026-07-19 | **Tags**: agents, ingest, provenance, approvals

### Problem
Publishing agent deliverables must not bypass governor approvals or provenance.

### Decision
Publish under `AGENT_ROOT/publishes/` with `origin=agent-generated`; approvals
in enforce mode; reuse supersede/rollback for retraction.

### Impact on developers
- Call `POST /agent/runs/{id}/publish`; expect ApprovalQueue when enforce.
- See [Agents](../tools/agents.md).

### Related
- [ADR-0007](../adr/0007-generated-content.md) · [ADR-0002](../adr/0002-ingest-supersede.md)

## 0008 — SPIRE / SPIFFE for agent identity

**Status**: Accepted | **Date**: 2026-07-21 | **Tags**: identity, spire, spiffe, agents, governor

### Problem
Agent mastering needs attested workload identity, not only human `user_space`.

### Decision
1. Compose profile `spire`; trust domain `tkeir.local`.
2. Agent ID shape `spiffe://{trust}/agent/{name}`.
3. `SPIFFE_MODE` / `SPIFFE_ENFORCE`; ActionRecord.actor.spiffe_id required when enforced.

### Impact on developers
- Set `SPIFFE_MODE=dev` locally; enable `spire` + `agents` in Compose for workload mode.
- See [SPIRE / SPIFFE](../deployment/spire.md).

### Related
- [ADR-0008](../adr/0008-spire-agent-identity.md)

## Cross-reference by concern

| Concern | Relevant ADRs |
|---------|--------------|
| deployment / profiles | 0001 |
| iam / identity / spiffe | 0001, 0004 (hist.), 0008 |
| audit / worm | 0001, 0003 |
| ingest / rollback | 0002, 0007 |
| agents / mcp / governance | 0005, 0007, 0008 |
| ontology / kg / vespa | 0006 |
| provenance / approvals | 0007 |

Checkpoint: each `##` section above maps to one file in `tkeir/docs/adr/000*.md`.
