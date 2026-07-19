# Ingestion (Phase 3)

The **tkeir-ingest** service exposes a push API for documents, stages them
under `staging/{doc_id}/`, writes an `ingest.manifest.json`, runs the NLP
pipeline, and indexes chunks into Vespa when `INGEST_INDEX_ENABLED=true`.
Indexed docs use Vespa **streaming** groups: the job’s `user_space` is the
Keycloak principal (or **`dev@tkeir`** when auth is off).

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ingest/document` | Multipart file **or** JSON `{"url": "..."}` |
| `POST` | `/ingest/batch` | JSON manifest of URL items |
| `GET` | `/ingest/status/{id}` | Job status + manifest |
| `GET` | `/health`, `/ready`, `/metrics` | Probes (same pattern as RAG API) |

Default port: **8091**.

## Idempotency

- `doc_id = sha256(content)`
- Idempotency key: `(doc_id, pipeline_config_sha256, embedder.sha256)`
- Re-ingesting the same triple returns **noop** (HTTP 202, status `noop`).

## Staging layout

```
${INGEST_ROOT}/
  staging/{doc_id}/
    source file
    pipeline.json
    ingest.manifest.json
  jobs/{ingest_id}.json
  dlq/{ingest_id}.json
  idempotency.json
```

Manifest schema: `thot/ingest/schemas/ingest.manifest.v1.json`.

## Auth and user space

When `INGEST_AUTH_ENABLED=true`, requests require a bearer token with scope
`intent:ingest` (Keycloak) or `INGEST_DEV_TOKEN` in development.

The actor (and Vespa `user_space`) is resolved from the Bearer JWT
(`preferred_username` → `email` → `sub`), else `VESPA_USER_SPACE` /
`dev@tkeir`. Status responses and job records store that space so indexing
and later supersede stay in the same streaming group.

## CLI — DLQ retry

```bash
tkeir-ingest retry --from-dlq --ingest-id <original-id>
```

## Compose

```bash
make compose-up PROFILES=core,auth,ingest
# With auth off / INGEST_DEV_TOKEN: indexes into VESPA_USER_SPACE (dev@tkeir).
# With a Keycloak bearer: indexes into that user's streaming group.
curl -F "file=@tkeir/tests/indexing/input/00163fe7688e71ce06f495a6811fef71.pdf" \
  http://localhost:8091/ingest/document
```

## Helm

Enable in umbrella values:

```yaml
ingest:
  enabled: true
```

Chart: `deploy/charts/tkeir-ingest` (PVC for `/var/tkeir/ingest`).

## Related

- [ADR-0002: Ingest supersede strategy](../adr/0002-ingest-supersede.md)
- [Compose profile](compose.md)
