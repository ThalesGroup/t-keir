# Governor (Phase 5)

`POST /governor/kill` toggles runtime flags; API and ingest workers consult
`GOVERNOR_MODE` and shared state before privileged operations.

## Compose

```bash
cp deploy/compose/.env.example deploy/compose/.env
make compose-up PROFILES=core,governor
# optional: GOVERNOR_MODE=enforce in .env
```

Governor API: http://localhost:8094 — HMI `/admin` proxies via `/api/governor/*`.

## Helm

Enable in profile values:

```yaml
governor:
  enabled: true
  mode: enforce
```

## CLI

```bash
tkeir-governor flags
tkeir-governor kill --scope ingest --active true --reason drill
tkeir-governor budgets --actor anonymous
```

## Related

- [Mastering of Action](../regularity-component/action-mastering.md)
- [Kill-switch runbook](../runbooks/kill-switch.md)
