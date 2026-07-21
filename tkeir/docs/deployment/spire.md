# SPIRE / SPIFFE (agents)

Agent workloads require a SPIFFE ID for identity and mastering
([ADR-0008](../adr/0008-spire-agent-identity.md)).

## Quick start

```bash
# Synthesized IDs (no SPIRE containers) — default for local agent runs
export SPIFFE_MODE=dev
export SPIFFE_ENFORCE=false
make agent

# Compose: SPIRE + agents
make compose-up PROFILES=spire,agents,governor,auth
```

Configs and join/register notes live under `deploy/spire/` (see that directory’s
README in the repository root).

## Identity shape

`spiffe://{SPIFFE_TRUST_DOMAIN}/agent/{agent_name}`  
Default trust domain: `tkeir.local`.

ActionRecords set `actor.type=agent`, `actor.id=<user_space>`,
`actor.spiffe_id=<SPIFFE ID>`.

## Related

- [Agents](../tools/agents.md)
- [Mastering of Action](../regularity-component/action-mastering.md)
- [Identity of Action](../regularity-component/action-identiy.md)
- [Compose](compose.md)
