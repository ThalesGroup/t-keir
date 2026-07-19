# ADR-0001 — Platform operations architecture

- **Status:** Accepted
- **Date:** 2026-07-17
- **Deciders:** T-KEIR maintainers
- **Tags:** deployment, iam, audit, profiles

## Context

T-KEIR 2.0.0 ships a working P0 developer path (`make setup` → pipeline → Vespa →
`tkeir-rag` → `tkeir-hmi`). Customers and internal platforms need progressive
installation (local → Compose → Kubernetes), attributable actions (human and
machine), auditable query/result chains, and technical evidence hooks aligned
with EU AI Act, CRA, NIS2, DORA, GDPR, and PLD — without claiming legal
compliance.

## Decision

1. **Profiles P0–P4** are value presets and installer detection outcomes, not
   forked configuration trees. P0 remains the fast contributor on-ramp.
2. **Layout** under `deploy/` (Compose, Helm umbrella + sub-charts, Keycloak
   realm, K3s/Lima, Kubeflow standalone, policies) and Python packages under
   `tkeir/thot/{action,governor,audit,ingest}/`. Extend `tkeir-hmi/`; never add
   a parallel `ui/`.
3. **Identity:** Keycloak realm `tkeir` is a first-class component (Compose
   `auth` profile, Helm optional dependency). BYO IdP via `keycloak.useExisting`
   / `oidc.*`. Machine actors use confidential clients; SPIFFE is optional
   (deferred — [ADR-0004](../adr/0004-defer-spire.md)).
4. **Action layer:** ActionRecord v1 with W3C correlation IDs; hot store =
   append-only PostgreSQL + hash chain; compliance tier = S3/MinIO **object
   lock** (WORM). Detailed store choice is ADR-0002 (Phase 4).
5. **Inference:** charts and Compose map onto existing env contract
   (`PROVIDER`, `EMBEDDING_MODEL`, `LLM_MODEL`, `OLLAMA_BASE_URL`, …) via
   `UnifiedLLMWrapper` — no new provider abstraction.
6. **CNI:** Cilium on Linux for P3; macOS P3 via Lima VM; flannel fallback
   still enforces standard NetworkPolicies (maturity downgrade documented).
7. **Supply chain:** pins in `deploy/versions.lock.yaml`; images at
   `ghcr.io/thalesgroup/t-keir`; digest-pinned bases; Cosign keyless in CI.
8. **Feature flags default safe:** governor `observe` in P1/P2, `enforce` in
   P3/P4.

## Consequences

- MkDocs gains Deployment, Compliance, Runbooks, ADR, and Regularity component sections.
- New Make targets are additive; existing CLI entry points are never renamed.
- Phased PRs (0→9) must leave `make ci` green and P0 working.

## Related

- [Installation profiles](../deployment/index.md)
- [Identity of Action](../regularity-component/action-identiy.md)
- [Mastering of Action](../regularity-component/action-mastering.md)
