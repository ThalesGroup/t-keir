# Mastering of Action

Runtime control properties enforced by `tkeir-governor`. Engineering design
only — **not legal advice**. AI Act Art. 14 (human oversight) is mapped via
technical hooks (kill switch, `/admin` panel, approval queue).

## Modes

| `governor.mode` | Profiles | Behavior |
|-----------------|----------|----------|
| `off` | rare local debug | No checks |
| `observe` | P1 / P2 default | Decide + record; do not block |
| `enforce` | P3 / P4 | Deny / escalate / freeze |

## Five properties

1. **Explicit, temporary, revocable authorization** — action tokens (JWT,
   TTL ≤ 300 s) via Keycloak token exchange (RFC 8693). Revocation list
   effective &lt; 2 s. **Agent workloads** carry a SPIFFE ID on every
   ActionRecord (`spiffe://{trust}/agent/{name}`); governor enforce denies
   agent intents without an allow-listed ID
   ([ADR-0008](../adr/0008-spire-agent-identity.md)).
2. **Intent–action alignment** — OAuth client scopes
   (`intent:search|ingest|index|delete|audit.read|admin.override`) mapped by
   the governor; Policy-as-Code (OPA/Rego in `deploy/policies/app/`). Mismatch →
   deny + `blocked` ActionRecord + approval queue.
3. **Operational-context validation** — probes (Vespa, index freshness,
   `PROVIDER` health, error rate) before privileged actions; out-of-band →
   freeze action class via `tkeir-runtime-flags` ConfigMap.
4. **Reversibility & safe state** — compensation plans before bulk
   index/delete; `POST /governor/rollback`; `make rollback-index RUN=…`.
5. **Consumable budgets** — per token/actor: docs indexed/deleted, LLM tokens,
   estimated cost. 80 % throttle; 100 % block + mandatory approval.

## Kill switch & oversight

`POST /governor/kill {scope: all|ingest|index|inference|hmi-write}` flips
runtime flags; workers check before and during long operations (target: stop
in-flight bulk index &lt; 2 s).

HMI **`/admin`** (role `tkeir-admin`): live action feed, approvals with full
ActionRecord context, budget gauges, kill switch, one-click rollback. Every
override is itself an ActionRecord (`intent: admin.override`).

## Phase delivery

| Phase | What lands |
|-------|------------|
| 1 (PR-1b) | Keycloak login + scopes; correlation ID in HMI; `/admin` stub |
| 4 | Full ActionRecords + WORM |
| 5 | Enforce mode, budgets, kill switch, approval panel e2e |

## Related

- [Identity of Action](action-identiy.md)
- [AI Act mapping](../compliance/ai-act.md) (Phase 9)
- [Kill-switch runbook](../runbooks/kill-switch.md)
