# ADR-0004 — Defer SPIRE / SPIFFE to late production

- **Status:** Superseded by [ADR-0008](0008-spire-agent-identity.md)
- **Date:** 2026-07-17
- **Superseded:** 2026-07-21
- **Deciders:** T-KEIR maintainers
- **Tags:** identity, spire, spiffe, deployment

## Context

ADR-0001 and the Regularity component identity model mention **SPIFFE SVIDs** for machine
actors in P3+. SPIRE (SPIFFE Runtime Environment) requires agents on every node,
a trust domain, and operational runbooks — overhead that does not help day-to-day
software development on Compose or k3d.

T-KEIR already attributes actions without SPIRE:

| Mechanism | Where |
|-----------|--------|
| W3C `traceparent` + `X-Correlation-Id` | All HTTP services (`ActionCorrelationMiddleware`) |
| JWT scopes → intents | Keycloak realm, governor policy |
| `ActionRecord.actor` | Hot audit store, WORM segments |
| Service identity | `TKEIR_SERVICE` env on each container |

There are **no SPIRE agents** in the current charts or Compose stack, and none
are planned until a customer cluster explicitly requires mTLS workload identity
beyond what the platform IdP and NetworkPolicies provide.

## Decision (historical)

1. **Do not install SPIRE** in P0–P2 (dev-local, Compose, k3d-dev) or during
   active feature work (Phases 3–6).
2. **Do not block P3 `k8s-secure`** on SPIRE. Secure profile means governor
   `enforce`, audit enabled, auth on, optional NetworkPolicies — not SPIRE.
3. **Reserve SPIFFE** for a future optional workstream when:
   - workloads run on multi-tenant clusters without shared JWT issuance, or
   - mTLS between services is mandated and cert rotation must be automatic.
4. Until then, populate `ActionRecord.actor.spiffe_id` only when explicitly set
   by an integrator; leave it `null` in default deployments.

## Supersession

Agent workloads (`tkeir-agent`) need attested machine identity for mastering
(kill switch `agents`, budgets, ActionRecord attribution). **ADR-0008** adopts
SPIRE/SPIFFE for the agent path while keeping non-agent services on JWT +
correlation until a later mesh workstream.

## Related

- [ADR-0008](0008-spire-agent-identity.md)
- [ADR-0001](0001-platform-architecture.md)
- [Secure cluster](../deployment/k8s-secure.md)
- [Identity of Action](../regularity-component/action-identiy.md)
