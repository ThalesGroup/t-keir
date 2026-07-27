# Ingestion (Phase 3)

The **tkeir-ingest** service exposes a push API for documents, stages them
under `staging/{doc_id}/`, writes an `ingest.manifest.json`, runs the NLP
pipeline, and indexes chunks into Vespa when `INGEST_INDEX_ENABLED=true`.
Indexed docs use Vespa **streaming** groups: the job’s `user_space` is the
Keycloak principal (or **`dev@tkeir`** when auth is off).

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ingest/document` | Multipart file **or** JSON `{"url": "..."}` (+ optional `ontologies`) |
| `POST` | `/ingest/batch` | JSON manifest of URL items (each may set `ontologies`) |
| `POST` | `/ingest/stop` | Stop the ingest process (client `--stop-on-failed`) |
| `GET` | `/ingest/status/{id}` | Job status + manifest |
| `GET` | `/health`, `/ready`, `/metrics` | Probes (same pattern as RAG API) |

Default port: **8091**.

### Stop on first failure

For fast debug loops, stop both server and client on the first failed document:

```bash
# Terminal A
make ingest STOP_ON_FAILED=1

# Terminal B
make datasets-ingest STOP_ON_FAILED=1
```

- Server: `INGEST_STOP_ON_FAILED=1` exits the process when a job fails.
- Client: `--stop-on-failed` cancels remaining uploads and calls `POST /ingest/stop`.

### Per-document external ontologies (client uploads content)

The ingest **server never reads client filesystem paths**. Ontologies must be
uploaded as **file bytes** in the same request as the document (same rule as
the document itself).

| Channel | How to send ontologies |
|---------|------------------------|
| Multipart | Repeatable `-F ontology_file=@domain.ttl` (content) |
| JSON | `"ontologies": [{"filename": "domain.ttl", "content_base64": "..."}]` |

The server stages uploads under `${INGEST_ROOT}/uploaded_ontologies/{id}/` and
passes those **server-local** paths to NER / syntax / document-ontology.

**Multipart**

```bash
curl -X POST http://localhost:8091/ingest/document \
  -F "file=@sitrep.txt" \
  -F "ontology_file=@/path/on/client/c2sim_combined.ttl" \
  -F "ontology_file=@/path/on/client/c2sim_c4isr.ttl" \
  -F 'metadata={"corpus":"osint","topic_id":"situational_awareness"}'
```

**JSON**

```bash
# content_base64 = base64 of the ontology file bytes (not a path string)
curl -X POST http://localhost:8091/ingest/document \
  -H "Content-Type: application/json" \
  -d '{
    "url": "file:///path/to/doc.txt",
    "ontologies": [
      {"filename": "c2sim_combined.ttl", "content_base64": "<base64>"},
      {"filename": "c2sim_core.owl", "content_base64": "<base64>"}
    ],
    "metadata": {"corpus": "osint"}
  }'
```

`make datasets-ingest` reads local files via `--ontology-dir` / `DATASETS_ONTOLOGY_DIR`
on the **client** and uploads each file’s bytes with every OSINT document.

Host ingest serializes the heavy NLP pipeline (`INGEST_MAX_CONCURRENCY=1` by
default). Raising concurrency often OOMs a laptop process (SIGKILL / exit 137)
because each job loads spaCy models. Prefer more upload workers only when the
server has headroom, and keep `make datasets-ingest` at `INGEST_WORKERS=1`.

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

Manifest schema: `thot/tools/ingest/schemas/ingest.manifest.v1.json`.

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

- [Compose profile](compose.md)
