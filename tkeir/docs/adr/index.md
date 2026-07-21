# Architecture Decision Records

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-platform-architecture.md) | Platform operations architecture | Accepted |
| [0002](0002-ingest-supersede.md) | Ingest supersede and rollback | Accepted (Phase 3) |
| [0003](0003-audit-store-worm.md) | Two-tier audit store + WORM | Accepted (Phase 4) |
| [0004](0004-defer-spire.md) | Defer SPIRE / SPIFFE (historical) | **Superseded** by [0008](0008-spire-agent-identity.md) |
| [0005](0005-agent-architecture.md) | Agent architecture (from-scratch runtime) | Accepted (Phase B–D) |
| [0006](0006-kg-store.md) | Per-tenant fused KG store | Accepted (Phase C) |
| [0007](0007-generated-content.md) | Agent-generated content publication | Accepted (Phase E) |
| [0008](0008-spire-agent-identity.md) | SPIRE / SPIFFE for agent identity & mastering | Accepted |

Further ADRs (Keycloak chart choice, CNI, full-mesh SPIFFE) land with later
workstreams.
