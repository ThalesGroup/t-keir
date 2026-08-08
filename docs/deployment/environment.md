# Environment variables

Reference for variables that configure T-KEIR services, Compose, and the HMI.
Defaults are **code-sourced** unless noted as Make/Compose-only.

**Compose:** copy [`deploy/compose/.env.example`](../../deploy/compose/.env.example)
to `deploy/compose/.env` (never commit secrets). Deep tables also live on
[Audit](audit.md), [Governor](governor.md), [SPIRE / SPIFFE](spire.md),
[Ingest](ingest.md), [Vespa RAG](../tools/vespa_rag.md), [Agents](../tools/agents.md),
[MCP](../tools/mcp.md), and [HMI](../hmi.md).

## Ports (host defaults)

| Port | Service |
|------|---------|
| 3000 | HMI (`tkeir-hmi`) |
| 3001 | Grafana (observability profile) |
| 8080 / 19071 | Vespa query / config |
| 8082 | Keycloak |
| 8090 | RAG API (`tkeir-api`) |
| 8091 | Ingest |
| 8092 | Agent |
| 8093 | **Audit** *or* **MCP** (same default — remap if both profiles) |
| 8094 | Governor |
| 8095 | OKF |
| 8096 | Web collector (`tkeir-collector`) |
| 8888 | SearXNG |
| 11434 | Ollama (often on the host) |

## Cross-cutting

| Variable | Default | Purpose |
|----------|---------|---------|
| `TKEIR_ENV` | `dev` | Environment label on ActionRecords / logs (`ENVIRONMENT` alias) |
| `TKEIR_SERVICE` | per-service | Service name in structured logs |
| `TKEIR_WORKSPACE` | Compose: `/workspace` | In-container corpus / ontology mount |
| `TKEIR_WORKSPACE_HOST` | `../../workspace` | Host path mounted into ingest |
| `TKEIR_ONTOLOGY_ROOT` | unset | Extra ontology root for derive-from |
| `VESPA_USER_SPACE` | `dev@tkeir` | Streaming group when auth is off / CLI |
| `GOVERNOR_MODE` | `observe` | `off` \| `observe` \| `enforce` (all services) |
| `PROVIDER` | `ollama` | `ollama` \| `openai` \| `vllm` |
| `TRANSFORMERS_CACHE` | Make: `.cache/models` | Hugging Face hub cache (rerankers, etc.; **not** BGE-M3) |
| `FORCE_BGE` | unset | Set `1` to re-download BGE into `tkeir/resources/modeling/net/bge-m3` |
| `WORKSPACE` | repo `workspace/` | Host Make workspace root |

### CORS

| Variable | Default | Service |
|----------|---------|---------|
| `RAG_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | RAG API |
| `INGEST_CORS_ORIGINS` | same | Ingest |
| `GOVERNOR_CORS_ORIGINS` | same | Governor |
| `AUDIT_CORS_ORIGINS` | same | Audit |
| `CORS_ALLOW_ORIGINS` | `*` | Agent / MCP HTTP |

## Vespa / RAG

| Variable | Default | Purpose |
|----------|---------|---------|
| `VESPA_URL` | `http://localhost:8080` (Compose: `http://vespa:8080`) | Document + search API |
| `VESPA_CONFIG_URL` | `http://localhost:19071` | Config server |
| `VESPA_TIMEOUT_SECONDS` | `60` | HTTP timeout |
| `RAG_HOST` / `RAG_PORT` | `0.0.0.0` / `8090` | RAG listen |
| `RAG_URL` | Make: `http://localhost:8090` | Clients / smoke / MCP fallback |

Values in `configs/rag.yaml` can override URL / timeout when env is unset.

## LLM / embeddings

Resolved by `UnifiedLLMWrapper` (`PROVIDER` → provider-specific defaults).

| Variable | Default | Purpose |
|----------|---------|---------|
| `PROVIDER` | `ollama` | Backend selector |
| `EMBEDDING_MODEL` | ollama: `bge-m3`; openai: `text-embedding-3-small`; vllm: `bge-small-en-v1.5` | Embedding model id |
| `LLM_MODEL` | ollama/vllm: `mistral-nemo`; openai: `gpt-4o` | Chat / generation |
| `EMBEDDING_DIM` | `1024` | Must match Vespa `dense_vector` dim (BGE-M3) |
| `RERANKER_MODEL` | unset | Optional CrossEncoder HF id (only if `RERANK_STRATEGY=cross_encoder`). Not used for dual-hybrid ColBERT |
| `RERANK_STRATEGY` | `embedding_cosine` | Legacy path: `embedding_cosine` \| `cross_encoder`. Production second stage is BGE-M3 ColBERT |
| `HTTP_TIMEOUT_SECONDS` | `120` | Provider HTTP timeout (embeddings / default client) |
| `LLM_GENERATE_TIMEOUT_SECONDS` | `max(HTTP_TIMEOUT, 600)` | Chat/completions timeout (persona wiki merges, agent loops). Raise further for slow local Ollama (e.g. `900`). |
| `OLLAMA_BASE_URL` | `http://localhost:11434` (Compose often `http://host.docker.internal:11434`) | Ollama |
| `OPENAI_API_KEY` | unset | OpenAI / compatible key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible base |
| `VLLM_BASE_URL` | `http://localhost:8000/v1` | vLLM OpenAI-compatible base |

## Auth / Keycloak

| Variable | Default | Purpose |
|----------|---------|---------|
| `AUTH_ENABLED` | Compose: `true`; local HMI: off unless `"true"` | Require Keycloak OIDC |
| `AUTH_SECRET` | Compose/dev string | Auth.js secret (**change in prod**) |
| `AUTH_URL` | `http://localhost:3000` | Canonical HMI URL / callbacks |
| `AUTH_KEYCLOAK_ID` | `tkeir-hmi` | OIDC client id |
| `AUTH_KEYCLOAK_SECRET` | `""` | Client secret if confidential |
| `AUTH_KEYCLOAK_ISSUER` | `http://localhost:8082/realms/tkeir` | Realm issuer |
| `AUTH_TRUST_HOST` | Compose: `true` | Trust `Host` behind proxy |
| `KEYCLOAK_ADMIN` | `admin` | Bootstrap admin user |
| `KEYCLOAK_ADMIN_PASSWORD` | `admin` | Bootstrap admin password |
| `KEYCLOAK_DB_PASSWORD` | `keycloak` | Keycloak Postgres password |

## Ingest

| Variable | Default | Purpose |
|----------|---------|---------|
| `INGEST_ROOT` | `/var/tkeir/ingest` | Job / staging root |
| `INGEST_HOST` / `INGEST_PORT` | `0.0.0.0` / `8091` | HTTP listen |
| `INGEST_PIPELINE_CONFIG` | `configs/pipeline.yaml` | Pipeline YAML |
| `INGEST_MAX_CONCURRENCY` | `1` | Concurrent NLP + index jobs |
| `INGEST_AUTH_ENABLED` | `false` | Require Bearer / intent |
| `INGEST_DEV_TOKEN` | unset | Dev Bearer when auth on |
| `INGEST_INDEX_ENABLED` | `true` | Index after pipeline |
| `INGEST_STOP_ON_FAILED` | `false` | Exit on first failed job |
| `INGEST_API_URL` | Make: `http://localhost:8091` | Corpus ingest client |
| `INGEST_TOKEN_URL` | Keycloak token endpoint | Client credentials (Make) |
| `INGEST_ROOT_HOST` | `$(WORKSPACE)/ingest` | Host path for local ingest |

## Audit

| Variable | Default | Purpose |
|----------|---------|---------|
| `AUDIT_HOT_STORE_URL` | unset | Hot store (`postgres://…` or `sqlite:…`) |
| `AUDIT_SINK_MODE` | `dual` if hot URL else `memory` | Emitter: `memory` \| `hot` \| `dual` |
| `AUDIT_WORM_ROOT` | `/var/tkeir/audit/worm` | Local WORM segments |
| `AUDIT_SUBJECT_KEYS_PATH` | `/var/tkeir/audit/subject_keys.db` | DSR / forget keys |
| `AUDIT_HOST` / `AUDIT_PORT` | `0.0.0.0` / `8093` | Audit HTTP |
| `AUDIT_AUTH_ENABLED` | `false` | Gate read APIs |
| `AUDIT_DEV_TOKEN` | unset | Dev Bearer |
| `AUDIT_DB_PASSWORD` | `audit` | Compose Postgres password |
| `AUDIT_URL` | HMI: `http://localhost:8093` | HMI proxy upstream |
| `AUDIT_WORM_S3_ENDPOINT` | unset → no mirror | MinIO / S3 endpoint |
| `AUDIT_WORM_S3_BUCKET` | `tkeir-worm` | Bucket |
| `AUDIT_WORM_S3_ACCESS_KEY` | `MINIO_ROOT_USER` / `minioadmin` | Access key |
| `AUDIT_WORM_S3_SECRET_KEY` | `MINIO_ROOT_PASSWORD` / `minioadmin` | Secret |
| `AUDIT_WORM_S3_REGION` | `us-east-1` | SigV4 region |
| `AUDIT_WORM_S3_PREFIX` | `segments/` | Object key prefix |
| `AUDIT_WORM_S3_OBJECT_LOCK` | on | COMPLIANCE object lock |
| `AUDIT_WORM_RETENTION_DAYS` | `30` | Retain-until / MinIO init |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | `minioadmin` | Object store bootstrap |

## Governor

| Variable | Default | Purpose |
|----------|---------|---------|
| `GOVERNOR_MODE` | `observe` | `off` \| `observe` \| `enforce` |
| `GOVERNOR_HOST` / `GOVERNOR_PORT` | `0.0.0.0` / `8094` | API listen |
| `GOVERNOR_STATE_ROOT` | `/var/tkeir/governor` (Make: `$(WORKSPACE)/governor`) | Shared flags / budgets / approvals |
| `GOVERNOR_FLAGS_PATH` | `{root}/flags.json` | Kill flags |
| `GOVERNOR_BUDGET_DB` | `{root}/budgets.db` | Budget SQLite |
| `GOVERNOR_APPROVALS_PATH` | `{root}/approvals.json` | Approval queue |
| `GOVERNOR_AUTH_ENABLED` | `false` | Gate admin APIs |
| `GOVERNOR_DEV_TOKEN` | unset | Admin Bearer shortcut |
| `GOVERNOR_DEFAULT_DOC_BUDGET` | `10000` | Default document budget |
| `GOVERNOR_DEFAULT_LLM_TOKEN_BUDGET` | `500000` | Default LLM token budget |
| `GOVERNOR_THROTTLE_RATIO` | `0.8` | Soft throttle threshold |
| `GOVERNOR_TOKEN_SECRET` | `dev-governor-token-secret-change-me` | HMAC for action tokens |
| `GOVERNOR_REVOKE_PATH` | `{root}/revoked.json` | Token revocation list |
| `GOVERNOR_URL` | `http://127.0.0.1:8094` (Compose: `http://tkeir-governor:8094`) | Clients / HMI |

## Agents / SPIFFE

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_ROOT` | `workspace/agent` (Compose: `/var/tkeir/agent`) | Run / publish store |
| `AGENT_HOST` / `AGENT_PORT` | `0.0.0.0` / `8092` | Agent HTTP |
| `AGENT_URL` | `http://localhost:8092` | HMI / Make |
| `TKEIR_AGENT_CONFIG_DIRS` | unset | Extra agent YAML dirs (`:` / `;` separated) |
| `TKEIR_AGENT_NAMES` | unset | Comma allow-list of agent stems for `tkeir-agent` |
| `WIKI_MATCH_THRESHOLD` | `0.15` | Jaccard floor to reuse closest user wiki |
| `AGENT_PUBLISH_OBSERVE_AUTO` | `1` | Auto-publish in observe mode |
| `SPIFFE_MODE` | `dev` | `off` \| `dev` \| `workload` |
| `SPIFFE_TRUST_DOMAIN` | `tkeir.local` | Trust domain |
| `SPIFFE_ID` | Compose: `spiffe://tkeir.local/agent/tkeir-agent` | Explicit workload ID |
| `SPIFFE_ID_FILE` | `/var/run/secrets/spiffe/spiffe_id` | File-based ID |
| `SPIFFE_ENDPOINT_SOCKET` | `unix:///run/spire/sockets/agent.sock` | Workload API socket |
| `SPIFFE_ENFORCE` | Compose: `false`; else follows governor enforce | Require allow-listed ID |
| `SPIFFE_AGENT_ID_PREFIX` | `spiffe://tkeir.local/agent/` | Allow-list (comma-separated) |
| `SPIRE_TAG` | `1.15.2` | SPIRE image tag |
| `SPIRE_JOIN_TOKEN` | unset | First SPIRE agent join |

## MCP

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_HOST` / `MCP_PORT` | `0.0.0.0` / `8093` | HTTP server |
| `MCP_AUTH_ENABLED` | `false` | Require Bearer / intent |
| `MCP_DEV_TOKEN` | unset | Dev Bearer |
| `MCP_RAG_URL` | Compose: `http://tkeir-api:8090` | Upstream for `rag_query` |
| `MCP_AUTHORIZATION` | unset | Default `Authorization` for tool calls |
| `MCP_GOVERNOR_MODE` | falls back to `GOVERNOR_MODE` | Override for MCP authz |
| `MCP_STDIO` | unset; `1` → stdio | Official MCP stdio mode |

## HMI (Next.js)

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEXT_PUBLIC_API_URL` | `/api` | Browser API base (BFF proxy) |
| `API_URL` | `http://localhost:8090` (Compose: `http://tkeir-api:8090`) | Server-side RAG upstream |
| `API_PROXY_TIMEOUT_MS` | `300000` | Upstream timeout (ms) |
| `AGENT_URL` | `http://localhost:8092` | Agent proxy |
| `GOVERNOR_URL` | `http://localhost:8094` | Governor proxy |
| `OKF_URL` | `http://localhost:8095` | OKF proxy |
| `AUDIT_URL` | `http://localhost:8093` | Audit proxy |

## Web collector / SearXNG

| Variable | Default | Purpose |
|----------|---------|---------|
| `SEARXNG_URL` | `http://127.0.0.1:8888` | Meta-search origin for `tkeir-collector` |
| `SEARXNG_IMAGE` | `docker.io/searxng/searxng:latest` | Image for `make pull-searxng` / `searxng-up` |
| `SEARXNG_PORT` | `8888` | Host port mapped to container `:8080` |
| `COLLECTOR_PORT` | `8096` | Collector FastAPI port |
| `COLLECTOR_MAX_RESULTS` | `5` | Default SearXNG hit cap |
| `COLLECTOR_SIMHASH_MAX_HAMMING` | `3` | Near-duplicate Hamming threshold |
| `COLLECTOR_BATCH_CONCURRENCY` | `4` | Max parallel queries in `/collect/batch` |
| `COLLECTOR_CORS_ORIGINS` | HMI origins | CORS allow-list |
| `TKEIR_SERVICE` | `tkeir-collector` (via Make) | JSON logs / ActionRecords |

Plus Auth / Keycloak variables above.

## Compose / images / observability

| Variable | Default | Purpose |
|----------|---------|---------|
| `IMAGE_REGISTRY` / `IMAGE_TAG` | `local` / `dev` | Image coordinates |
| `PROFILES` | Make: `core,auth` | Compose profile list |
| `MODEL_MODE` | `fetch` | Build-time model fetch |
| `VERSION` / `GIT_COMMIT` / `BUILD_DATE` | git describe / … | Image labels |
| `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` | `admin` | Grafana UI |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | Optional OTLP metrics |

## Secrets checklist

Change these before any shared or production deploy:

- `AUTH_SECRET`, Keycloak admin / DB passwords
- `GOVERNOR_TOKEN_SECRET`
- `MINIO_ROOT_*`, `AUDIT_DB_PASSWORD`, Grafana passwords
- `OPENAI_API_KEY` (and any provider credentials)
- `SPIRE_JOIN_TOKEN` (when using the `spire` profile)

Do not commit `deploy/compose/.env` or real tokens into the repository.

## Related

- [Compose](compose.md)
- [Deployment profiles](index.md)
- [Operation and Management](../oam.md)
- [Security](../security.md)
