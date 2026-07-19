# Kill-switch runbook

Emergency stop for ingest, indexing, inference, or all write paths.

## Trigger (Compose / CLI)

```bash
# Activate ingest kill
GOVERNOR_STATE_ROOT=/var/tkeir/governor tkeir-governor kill \
  --scope ingest --active true --reason "incident-123"

# Or via HTTP (requires intent:admin.override when auth enabled)
curl -X POST http://localhost:8094/governor/kill \
  -H 'content-type: application/json' \
  -d '{"scope":"ingest","active":true,"reason":"incident-123"}'
```

HMI: open `/admin` as a user with role `tkeir-admin` and use **Kill** buttons
(scopes include **`agents`** for the agent runtime).

## Verify

```bash
tkeir-governor flags
curl -s http://localhost:8094/governor/flags | jq .
```

In-flight ingest jobs fail fast with `governor kill switch active for ingest`.

## Release

```bash
tkeir-governor kill --scope ingest --active false --reason cleared
```

Global kill (`scope=all`) stops every scoped class until released.

## Related

- [Governor deployment](../deployment/governor.md)
- [Mastering of Action](../regularity-component/action-mastering.md)
