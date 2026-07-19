# Runbooks

Operational procedures for the platform layer:

| Runbook | When |
|---------|------|
| [Kill switch](kill-switch.md) | Emergency stop (incl. `agents`) |
| [Agent runaway](agent-runaway.md) | Budget burn / stuck agent loop |
| [Injection incident](injection-incident.md) | Prompt injection in corpus/tools |
| [Retract generated content](retract-generated.md) | Unpublish agent-generated docs |
| Incident / early-warning templates | Phase 9 (`tkeir-audit incident`) |
| Rollback index | `make rollback-index RUN=…` |
| Data subject request (DSR) | Phase 9 |
| Vespa backup / restore | Phase 6+ |
| Audit store / WORM restore | Phase 4 |

See also [Deployment profiles](../deployment/index.md).
