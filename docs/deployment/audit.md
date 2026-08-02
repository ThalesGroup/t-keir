# Audit store

Two-tier **ActionRecord** storage for identity and compliance: a **hot** query
store (hash-chained, append-only) and a **WORM** archive (immutable segments,
optional object-lock mirror).
ActionRecord shape and correlation: [Identity of Action](../regularity-component/action-identiy.md).

Engineering documentation only — **not legal advice**.

## Architecture

```mermaid
flowchart LR
  subgraph emitters [Emitters]
    API[tkeir-api middleware]
    ING[tkeir-ingest]
    AG[tkeir-agent AgentGuard]
  end
  subgraph sink [Action sink]
    MEM[memory]
    HOT[Hot store SQLite / Postgres]
  end
  subgraph worm [WORM]
    FS["AUDIT_WORM_ROOT .jsonl.gz + .sha256"]
    S3[MinIO / S3 object-lock]
  end
  AUD[tkeir-audit API / CLI]
  emitters --> sink
  HOT --> AUD
  AUD -->|archive| FS
  FS -->|optional mirror| S3
```

| Component | Role |
|-----------|------|
| `tkeir-audit` (`:8093`) | Query, report, verify, archive, forget |
| Hot store | PostgreSQL (Compose) or SQLite (local/tests); hash chain + `archive_refs` |
| WORM | `AUDIT_WORM_ROOT` segments; optional MinIO when `AUDIT_WORM_S3_ENDPOINT` is set |
| Subject keys | Separate SQLite for GDPR-style crypto-shred (`forget`) — outside WORM |

Services that emit ActionRecords (API correlation middleware, agent guard, etc.)
use `default_action_sink()` from `thot.audit`. The audit service itself reads
the same hot/WORM configuration for reports and verification.

## Sink modes

| `AUDIT_SINK_MODE` | Behavior |
|-------------------|----------|
| `memory` | In-process only (lost on restart) |
| `hot` | Hot store only |
| `dual` | Memory + hot; hot write failures are logged and swallowed |

**Default:** `dual` when `AUDIT_HOT_STORE_URL` is set, otherwise `memory`.

Compose `tkeir-api` defaults to `AUDIT_SINK_MODE=memory` unless you set a hot
URL (and typically `dual`) in `.env`. Enabling the `audit` profile alone does
**not** automatically point the API at Postgres — wire both:

```bash
AUDIT_SINK_MODE=dual
AUDIT_HOT_STORE_URL=postgres://audit:audit@audit-db:5432/audit
```

## Hot store

| URL scheme | Backend | Notes |
|------------|---------|--------|
| `sqlite:` / `file:` | `SqliteHotStore` | Local / tests |
| `postgres:` / `postgresql:` | `PostgresHotStore` | Needs `psycopg`; append-only triggers block UPDATE/DELETE |

Records are sealed with a hash chain (`prev_hash` → `record_hash`). Archiving
adds `archive_refs` without mutating sealed payloads.

## WORM segments

- Root: `AUDIT_WORM_ROOT` (default `/var/tkeir/audit/worm`).
- Per segment: `{segment_id}.jsonl.gz` + `{segment_id}.sha256`.
- URI form: `worm://{segment_id}`.
- Daily anchors: `{root}/anchors/{YYYY-MM-DD}.json` via `write_anchor`.
- Archive batch: up to 500 unarchived hot rows → segment + mark archived.

Local WORM is authoritative for `audit-verify`. Optional S3 mirror failures are
logged; they do not roll back the local segment write.

### MinIO / object-lock mirror

Triggered after a local segment write when `AUDIT_WORM_S3_ENDPOINT` is set.

| Variable | Default |
|----------|---------|
| `AUDIT_WORM_S3_ENDPOINT` | unset → no mirror |
| `AUDIT_WORM_S3_BUCKET` | `tkeir-worm` |
| `AUDIT_WORM_S3_ACCESS_KEY` | `MINIO_ROOT_USER` or `minioadmin` |
| `AUDIT_WORM_S3_SECRET_KEY` | `MINIO_ROOT_PASSWORD` or `minioadmin` |
| `AUDIT_WORM_S3_REGION` | `us-east-1` |
| `AUDIT_WORM_S3_PREFIX` | `segments/` |
| `AUDIT_WORM_S3_OBJECT_LOCK` | on (`COMPLIANCE` + retain-until) unless falsy |
| `AUDIT_WORM_RETENTION_DAYS` | `30` |

```bash
make compose-up PROFILES=core,objectstore,audit
# deploy/compose/.env:
# AUDIT_WORM_S3_ENDPOINT=http://minio:9000
```

## Privacy / forget

`SubjectKeyStore` at `AUDIT_SUBJECT_KEYS_PATH` (default
`/var/tkeir/audit/subject_keys.db`) holds envelope keys used to pseudonymize
subjects. `tkeir-audit forget --subject …` crypto-shreds the key so historical
WORM bytes remain intact while subject linkage is destroyed.

## Configuration

| Variable | Default | Notes |
|----------|---------|--------|
| `AUDIT_HOT_STORE_URL` | unset | Required for durable hot tier / CLI; host Make uses `sqlite:workspace/audit/hot_store.db` |
| `AUDIT_WORM_ROOT` | `workspace/audit/worm` (host) | Segment filesystem root; Compose may use `/var/tkeir/audit/worm` |
| `AUDIT_SUBJECT_KEYS_PATH` | `workspace/audit/subject_keys.db` (host) | Forget keys |
| `AUDIT_HOST` / `AUDIT_PORT` | `0.0.0.0` / `8093` | HTTP listen |
| `AUDIT_SINK_MODE` | `dual` if hot URL else `memory` | Emitter side |
| `AUDIT_AUTH_ENABLED` | `false` | Gate read APIs |
| `AUDIT_DEV_TOKEN` | unset | Bearer shortcut when auth on |
| `AUDIT_CORS_ORIGINS` | localhost:3000 variants | Comma-separated |
| (+ S3 vars above) | | Optional; leave unset when not using MinIO |

On the host, `make audit-*` always reads **`workspace/audit`** (hot sqlite + `worm/`). MinIO is not required — it is only an optional WORM mirror when `AUDIT_WORM_S3_ENDPOINT` is set. Host `make rag|agent|ingest|okf|mcp` now export the same `AUDIT_*` so ActionRecords land in that directory.

## HTTP API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | no | Liveness |
| `GET` | `/ready` | no | 503 if hot store missing |
| `GET` | `/metrics` | no | Prometheus text |
| `GET` | `/audit/actions` | audit | Filters: `correlation_id`, `actor`, `from`, `to`, `limit`, `offset` |
| `GET` | `/audit/report` | audit | `correlation_id`, `format=json\|html` |
| `POST` | `/audit/archive` | audit | Export unarchived → WORM; returns `{segment_id}` |
| `GET` | `/audit/verify` | audit | Hot chain + WORM sidecar checks |

When `AUDIT_AUTH_ENABLED=true`, callers need scope `intent:audit.read`, role
`auditor`, or `AUDIT_DEV_TOKEN`.

HMI deep-links and BFF proxy: `/api/audit/*` → `tkeir-audit`.

## CLI

Entry point: `tkeir-audit` (requires `AUDIT_HOT_STORE_URL` or exits 1).

| Command | Purpose |
|---------|---------|
| `report` | Correlation report |
| `summary --last 24h` | Recent activity summary |
| `verify` | Hot hash chain + WORM digests |
| `archive` | Close a WORM segment batch |
| `forget --subject …` | Crypto-shred subject key |
| `incident --kind early-warning\|72h\|final` | Incident evidence helpers |

## Make targets

```bash
make audit-report CID=<correlation-id> # FORMAT=json|html
make audit-summary                      # LAST=24h
make audit-verify                       # reads workspace/audit (no MinIO)
make audit-archive
make audit-evidence # compliance evidence pack
```

## Compose

```bash
export AUDIT_HOT_STORE_URL=postgres://audit:audit@audit-db:5432/audit
export AUDIT_SINK_MODE=dual
make compose-up PROFILES=core,audit
```

| Service | Profile | Notes |
|---------|---------|--------|
| `audit-db` | `audit` | Postgres DB `audit` |
| `tkeir-audit` | `audit` | Hot URL → `audit-db`; volume `audit_worm` |
| `minio` (+ init) | `objectstore` (+ ingest/audit) | Optional WORM mirror |

**Port note:** Compose also maps `tkeir-mcp` to host **8093** by default. Do not
run `audit` and `mcp` profiles on the same host without remapping one port.

## Verify flow

1. Emit actions with `AUDIT_SINK_MODE=dual` and a hot URL.
2. `GET /audit/actions?correlation_id=…` or `make audit-report CID=…`.
3. `make audit-archive` (or `POST /audit/archive`).
4. `make audit-verify` — recompute hot `record_hash` continuity and check WORM
   sidecar SHA-256 files.

## Related

- [Environment variables](environment.md)
- [Identity of Action](../regularity-component/action-identiy.md)
- [Governor](governor.md)
- [SPIRE / SPIFFE](spire.md) (agent `actor.spiffe_id` on records)
- [Compose](compose.md)
- [DSR runbook](../runbooks/dsr.md) (subject rights / forget)
