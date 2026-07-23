# Runbook — Agent runaway

Stop a runaway agent / workflow (budget burn, loop, unexpected tool fan-out).

## Immediate actions

1. Activate kill switch scope **`agents`** (stops in-flight steps &lt; ~2s):

```bash
make governor-kill SCOPE=agents ACTIVE=true
# or
curl -X POST http://localhost:8094/governor/kill \
  -H 'content-type: application/json' \
  -d '{"scope":"agents","active":true,"reason":"agent-runaway"}'
```

2. Cancel the specific run if known:

```bash
curl -X POST "http://localhost:8092/agent/runs/${RUN_ID}/cancel"
```

3. Confirm: `GET /agent/runs/{id}` → `killed` / `cancelled`; check ApprovalQueue
   for budget blocks.

## Aftermath

- Inspect steps + blackboard under `AGENT_ROOT/runs/{run_id}/`.
- Review ActionRecords for `actor.type=agent` and the run's `correlation_id`.
- Release kill when safe: `ACTIVE=false`.

## Related

- [Kill switch](kill-switch.md)
- [Agents](../tools/agents.md)
- ADR-0005
