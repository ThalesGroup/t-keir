# Audit store (Phase 4)

Two-tier ActionRecord storage: **hot** (query) + **WORM** (compliance archive).

## Components

| Component | Role |
|-----------|------|
| `tkeir-audit` (:8093) | Audit API + archiver CLI |
| Hot store | PostgreSQL (prod/compose) or SQLite (tests) |
| WORM | Local `AUDIT_WORM_ROOT` segments; optional MinIO mirror when
`AUDIT_WORM_S3_ENDPOINT` is set (object-lock COMPLIANCE on `tkeir-worm`) |

## MinIO / object-lock (Compose `objectstore`)

```bash
make compose-up PROFILES=...,objectstore,audit
# .env: AUDIT_WORM_S3_ENDPOINT=http://minio:9000
```

Archive writes local gzip segments then mirrors to `s3://tkeir-worm/segments/…`
with retention from `AUDIT_WORM_RETENTION_DAYS`. Mirror failures are logged;
local WORM remains authoritative for `audit-verify`.

## Wiring services

Set on API, ingest, and audit containers:

```bash
AUDIT_SINK_MODE=dual
AUDIT_HOT_STORE_URL=postgres://audit:audit@audit-db:5432/audit
```

ActionRecords from middleware are mirrored to the hot store automatically.

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/audit/actions` | Paginated search |
| `GET` | `/audit/report?correlation_id=` | Full causal chain |
| `GET` | `/audit/verify` | Hash-chain + WORM check |
| `POST` | `/audit/archive` | Manual segment export |

Auth: scope `intent:audit.read` when `AUDIT_AUTH_ENABLED=true`.

## CLI / Make

```bash
make audit-report CID=<correlation-id>
make audit-verify AUDIT_HOT_STORE_URL=sqlite:////tmp/audit.db
tkeir-audit archive
tkeir-audit incident --kind early-warning
tkeir-audit forget --subject <subject-id>
tkeir-audit forget --subject <keycloak-sub>
```

## Compose

```bash
export AUDIT_HOT_STORE_URL=postgres://audit:audit@audit-db:5432/audit
export AUDIT_SINK_MODE=dual
make compose-up PROFILES=core,audit
```

## Related

- [ADR-0003](../adr/0003-audit-store-worm.md)
- [Identity of Action](../regularity-component/action-identiy.md)
