# Docker Compose (P1+)

Bring up a full demo stack on macOS (Apple Silicon) or Linux without Kubernetes.
**P0 development** runs T-KEIR tools on the host (`make rag`, `make ingest`,
`uv`) and only containers Vespa — see [Zero to Hero §3–4](../zero_to_hero.md).

```bash
# Copy env defaults once (IMAGE_REGISTRY=local by default)
cp deploy/compose/.env.example deploy/compose/.env
```

Variable reference: [Environment variables](environment.md).

```bash
# Build images into the local Docker daemon (not GHCR)
make images # tags: local/tkeir-*:$IMAGE_TAG
# or: make image-api image-hmi …

# Start core + Keycloak
make compose-up PROFILES=core,auth

# Deploy Vespa passage schemas (doc_base / global / user) into Compose Vespa
# (required once after a fresh vespa_data volume — otherwise tkeir-api /health is 503)
make compose-bootstrap
docker restart tkeir-api

# Tail logs
make compose-logs

# Tear down (volumes kept). Full wipe including host DBs: make down
make compose-down
# Wipe Compose named volumes only:
make compose-down VOLUMES=1
```

Publish (CI / shared registry) is explicit:

```bash
make images-push IMAGE_REGISTRY=ghcr.io/thalesgroup/t-keir
```

## Compose profiles

| Profile | Services | Host ports |
|---------|----------|------------|
| `core` | vespa, tkeir-api, tkeir-indexer, tkeir-hmi | 3000, 8080, 8090, 19071 |
| `auth` | keycloak + postgres | **8082** (8080 is Vespa) |
| `ingest` | tkeir-ingest | 8091 |
| `audit` | tkeir-audit + postgres | 8093 |
| `governor` | tkeir-governor | 8094 |
| `okf` | tkeir-okf | 8095 |
| `observability` | otel-collector, prometheus, loki, tempo, grafana | **3001**, 9090, 3100, 3200, 4317/4318 |
| `objectstore` | minio (+ bucket init) | **9000**, 9001 |
| `mcp` | tkeir-mcp | 8093 (when not conflicting) |
| `agents` | tkeir-agent | **8092** |
| `spire` | spire-server, spire-agent | Workload API socket (internal) |

Example full demo stack:

```bash
make compose-up PROFILES=core,auth,ingest,audit,governor,observability,objectstore,agents,spire
```

Agent SPIFFE: [SPIRE / SPIFFE](spire.md).

After `make compose-up`, run `make compose-smoke` to verify health endpoints
(including Grafana/MinIO when those profiles are up).
Add `COMPOSE_SMOKE_RAG=1` for a minimal `/rag/query` check (requires warm models).
When audit is up, smoke asserts `X-Correlation-Id` can be resolved via the
audit report path.

## Inference on macOS

Prefer **Ollama on the host** (Metal):

```bash
export OLLAMA_BASE_URL=http://host.docker.internal:11434
export PROVIDER=ollama
# already set in deploy/compose/.env.example
```

## OIDC (Keycloak) and Vespa user space

Realm `tkeir` is imported from `deploy/keycloak/realm-tkeir.json`.
Vespa runs in **streaming mode**: each principal owns a group
(`streaming.groupname` / `g=<user_space>`).

| Mode | Vespa group |
|------|-------------|
| Keycloak signed-in | `preferred_username` → `email` → `sub` |
| Auth off / CLI indexer | `VESPA_USER_SPACE` (default **`dev@tkeir`**) |

| User | Password | Roles | Clearance | Typical Vespa group |
|------|----------|-------|-----------|---------------------|
| `demo-user` | `demo-user` | `tkeir-user` | `UNCLASSIFIED` | `demo-user` |
| `demo-auditor` | `demo-auditor` | auditor + user | `FOUO` | `demo-auditor` |
| `demo-admin` | `demo-admin` | `tkeir-admin`, `c2-admin` | `SECRET` | `demo-admin` |
| `analyst` | `analyst` | `c2-j2-analyst`, `tkeir-user` | `SECRET` | `analyst` |
| `moc-watch` | `moc-watch` | `c2-moc-watch`, `tkeir-user` | `FOUO` | `moc-watch` |
| `humint` | `humint` | `c2-j2x-humint`, `tkeir-user` | `SECRET` | `humint` |
| `commander` | `commander` | `c2-ctf-commander`, `tkeir-user` | `SECRET` | `commander` |
| `c2-admin` | `c2-admin` | `c2-admin` (+ admin composite) | `SECRET` | `c2-admin` |

These accounts are imported automatically from `deploy/keycloak/realm-tkeir.json`
when Keycloak starts with `--import-realm` (`make keycloak-up` /
`PROFILES=auth`). Password = username for every demo account.

`make keycloak-up` also runs **`make keycloak-sync-demo-users`**, which
idempotently creates/updates persona users, roles, and the `clearance` claim
via the Admin API (needed when the Keycloak volume was created before those
users existed in the realm JSON). You can re-run sync alone anytime:

```bash
make keycloak-sync-demo-users
```

If you prefer a clean reimport instead:

```bash
make compose-down VOLUMES=1 PROFILES=auth
make keycloak-up
```

Emails in the realm are `*@tkeir` (fallback if `preferred_username` is absent).

Admin console: http://localhost:8082 (bootstrap user `admin` / `admin` from `.env`).

Local HTTP is intentional for the hybrid demo: Compose sets
`KC_HOSTNAME=http://localhost:8082` / `KC_HOSTNAME_ADMIN=http://localhost:8082`
and `make keycloak-sync-demo-users` will set `master.sslRequired=NONE` if an
older volume still returns `HTTPS required` on the admin token endpoint.

HMI (`AUTH_ENABLED=true` in Compose) redirects unauthenticated browsers to Keycloak
and forwards `Authorization: Bearer <access_token>` on `/api/*` proxies so the RAG
API and ingest resolve the caller’s space. For local P0 without login:
`AUTH_ENABLED=false npm run dev` in `tkeir-hmi/` (searches **`dev@tkeir`**).

See [Zero to Hero §5](../zero_to_hero.md#5-p1-docker-compose-full-demo) and
[Vespa RAG — user space](../tools/vespa_rag.md#user-space-streaming-group).

## Correlation ID

Each `/rag/query` response carries `X-Correlation-Id`. The HMI shows it under the
answer with copy + “Audit this answer” (opens `/admin?correlation_id=…`).

## Images

See `deploy/images/README.md` and
`deploy/versions.lock.yaml`.
