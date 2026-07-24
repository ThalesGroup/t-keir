# Identity of Action

Design requirements for attributable, correlatable actions in T-KEIR.
This is an engineering design document, **not legal advice**.

## Goal

Every query, ingest, index, delete, admin override, auth lifecycle event, and
**agent** plan/step/tool invoke is attributable to a managed identity (human
Keycloak `sub`, service client, or **agent SPIFFE ID**) and joinable through a
**Correlation ID** (W3C trace-id).

Agent workloads obtain SPIFFE IDs via SPIRE (
Compose profile `spire`). Non-agent services may still omit `spiffe_id` until
mesh expansion.

## ActionRecord v1 (summary)

One JSON-Schema-validated record per action. Core fields:

| Field | Role |
|-------|------|
| `action_id` | ULID |
| `correlation_id` | 32-hex W3C trace-id |
| `actor` | `human` \| `service` \| `agent` + id (+ **`spiffe_id` required for agents**) |
| `delegation_chain` | Token-exchange hops (`jti`, clients, expiry) |
| `intent` | Declared from OAuth scope (`intent:search`, …) |
| `decision` | allow \| deny \| escalate + policy rules + model SHAs |
| `execution` / `result` | Timings, status, doc/chunk IDs, hashes |
| `evidence` | `prev_hash`, `record_hash`, WORM segment ref, signature |

Full schema: `tkeir/thot/action/schemas/action.v1.json` (Pydantic model
`thot.action.models.ActionRecord`).

## Correlation backbone

1. Accept inbound `traceparent`; else generate.
2. Propagate HMI proxy → API → Vespa client → `UnifiedLLMWrapper` → ingest/index.
3. Return `X-Correlation-Id` on every HTTP response; HMI shows copy + audit link.

## Two-tier audit store

| Tier | Technology | Role |
|------|------------|------|
| Hot | PostgreSQL append-only (triggers block UPDATE/DELETE) + hash chain | Report SLO &lt; 5 s p95 |
| WORM | S3/MinIO object lock (COMPLIANCE default; GOVERNANCE non-prod) | Immutable archive + anchors |

Verification: `tkeir-audit verify` re-hashes hot chain and cross-checks WORM
segments. GDPR: pseudonymize subjects; crypto-shred keys outside WORM
(`tkeir-audit forget`). Query text off by default (`request_hash` only).

Ops:
[Audit store](../deployment/audit.md) (Phase 4).

## Maturity mapping

| Level | Profile | Guarantees |
|-------|---------|------------|
| **M1** | P2+ | Correlated records, signed images, audit reports |
| **M2** | P3 | Keycloak actors, token-exchange delegation, OPA SHA, hash chain + WORM + anchors; **agent SPIFFE** |
| **M3** | P4 (partial) | Instant revocation, proof-cost telemetry; adaptive policies = future |

## Emission points (target)

FastAPI middleware (parent + children: `vespa.query`, `inference.generate`,
`rerank.score`, `ontology.fuse`); indexer; ingest manifests; governor decisions;
HMI admin ops; Keycloak auth events.

## Related

- [Mastering of Action](action-mastering.md)
- [Audit store](../deployment/audit.md)
- [SPIRE / SPIFFE](../deployment/spire.md)
- [GDPR mapping](../compliance/gdpr.md) (Phase 9)
