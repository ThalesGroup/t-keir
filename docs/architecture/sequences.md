# Data flows and sequences

Sequence diagrams for the main HTTP and background paths discovered under
`tkeir/thot/`. Participants use Compose / CLI service names. Middleware:
`ActionCorrelationMiddleware` (`thot.action.middleware`) and optional
`GovernorEnforceMiddleware` (`thot.governor.middleware`).

## Primary read path — RAG query

Triggered by `POST /rag/query` on `tkeir-api` (`thot.tools.search.app`). The
HMI proxies through Next.js to the API. Search hits Vespa hybrid search;
embeddings / generation use `UnifiedLLMWrapper`. Observable outcome: JSON
`QueryResponse` plus `X-Correlation-Id`.

```mermaid
sequenceDiagram
  actor User
  participant HMI as "tkeir-hmi :3000"
  participant API as "tkeir-api :8090"
  participant MW as ActionCorrelationMiddleware
  participant Vespa as "vespa :8080"
  participant LLM as UnifiedLLMWrapper

  User->>HMI: RAG query (browser)
  HMI->>API: POST /rag/query
  API->>MW: ensure correlation_id
  Note over API: resolve_vespa_user_space from JWT
  API->>LLM: embed / generate as configured
  API->>Vespa: PassageRetrievalPipeline (global/user)
  Vespa-->>API: passage hits
  API-->>HMI: QueryResponse + X-Correlation-Id
  HMI-->>User: results UI
```

Checkpoint: with `make rag` and indexed docs, `POST http://localhost:8090/rag/query` returns 200.

## Primary write path — ingest → index

Triggered by `POST /ingest/document` or `POST /ingest/batch` on
`tkeir-ingest` (`thot.tools.ingest.app`), or by CLI `tkeir-pipeline` +
`tkeir-index-documents`. Idempotency uses
`(doc_id, pipeline_config_sha256, embedder.sha256)`.

```mermaid
sequenceDiagram
  actor Client
  participant Ingest as "tkeir-ingest :8091"
  participant Store as IngestStore
  participant Pipe as tkeir-pipeline
  participant Index as tkeir-index-documents
  participant Vespa as "vespa :8080"

  Client->>Ingest: POST /ingest/document
  Ingest->>Store: write staging + ingest.manifest.json
  Note over Ingest: noop if digests unchanged
  Ingest-->>Client: IngestAcceptedResponse
  Ingest->>Pipe: run NLP pipeline on content
  Pipe->>Index: upsert passages
  Index->>Vespa: document API (global and/or user group)
  Client->>Ingest: GET /ingest/status/ingest_id
  Ingest-->>Client: IngestStatusResponse
```

Checkpoint: `GET /ingest/health` and status polling after a document POST.

## Authentication / authorisation path

Keycloak issues tokens (realm `tkeir`, host port **8082**). HMI uses Auth.js
OIDC when `AUTH_ENABLED=true`. RAG / agent resolve Vespa `user_space` from
JWT `preferred_username` → `email` → `sub`
(`thot.tools.search.user_space.resolve_vespa_user_space`). Agents also attach
SPIFFE IDs (`thot.agent.spiffe`).

```mermaid
sequenceDiagram
  actor User
  participant HMI as tkeir-hmi
  participant KC as "keycloak :8082"
  participant API as "tkeir-api or tkeir-agent"
  participant Vespa as vespa

  User->>HMI: sign in
  HMI->>KC: OIDC token
  KC-->>HMI: access_token
  HMI->>API: Authorization Bearer
  Note over API: decode JWT preferred_username claims
  API->>API: normalize_user_space to streaming group
  API->>Vespa: streaming.groupname equals user_space
```

Checkpoint: password grant with `tkeir-cli` yields `preferred_username` in the access token.

## Agent / workflow execution path

`POST /agent/runs` on `tkeir-agent` (`thot.tools.agent`) enqueues
`RunState`, then `AgentLoop` or `Orchestrator`. `AgentGuard` checks kill
switch scope `agents`, budgets, and SPIFFE; emits `ActionRecord`s.

```mermaid
sequenceDiagram
  actor Client
  participant Agent as "tkeir-agent :8092"
  participant Guard as AgentGuard
  participant Runner as "AgentLoop or Orchestrator"
  participant API as "tkeir-api or MCP tools"
  participant Gov as governor_state

  Client->>Agent: POST /agent/runs
  Agent->>Agent: resolve user_space and spiffe_id
  Agent-->>Client: run_id queued
  Agent->>Runner: asyncio task
  Runner->>Guard: check_step kill budget SPIFFE
  Guard->>Gov: flags / approvals
  alt denied
    Guard-->>Runner: deny
  else allow
    Runner->>API: tool invoke search rag
    Runner->>Guard: emit ActionRecord
  end
  Client->>Agent: GET /agent/runs/run_id
  Agent-->>Client: RunState + steps
```

Checkpoint: `GET /agent/ready` shows `spiffe_id`; run create returns `spiffe_id`.

## Audit / observability path

`ActionCorrelationMiddleware` generates or propagates W3C trace ids.
Services append `ActionRecord` via `default_action_sink`. Audit service
exposes `GET /audit/actions`, `GET /audit/report`, `POST /audit/archive`,
`GET /audit/verify` (`thot.audit.app`). Hot store is PostgreSQL; WORM uses
MinIO object lock when configured.

```mermaid
sequenceDiagram
  participant API as "tkeir-api or tkeir-agent"
  participant MW as ActionCorrelationMiddleware
  participant Sink as ActionSink
  participant Audit as "tkeir-audit :8093"
  participant PG as audit-db
  participant MinIO as "minio :9000"

  API->>MW: request
  MW->>MW: correlation_id equals trace-id
  API->>Sink: append ActionRecord
  Note over Sink: hash chain hot path
  Audit->>PG: query actions by correlation
  Audit->>MinIO: archive WORM segment
  Audit-->>API: report / verify
```

Checkpoint: response header `X-Correlation-Id` resolves via audit report when audit profile is up.

## Background / async path

`tkeir-indexer` (Compose `core`) and CLI `tkeir-index-documents` batch-index
pipeline JSON. Agent runs are `asyncio` tasks on the agent process. Audit
`POST /audit/archive` seals WORM segments. No Celery/RQ consumer was found in
`thot/`.

```mermaid
sequenceDiagram
  participant Cron as "tkeir-indexer or operator"
  participant Index as tkeir-index-documents
  participant Vespa as vespa
  participant Agent as tkeir-agent
  participant Runner as AgentLoop

  Cron->>Index: scan pipeline output dir
  Index->>Vespa: upsert passages (global / user)
  Note over Agent: POST /agent/runs schedules asyncio task
  Agent->>Runner: background run
  Runner-->>Agent: persist RunState under AGENT_ROOT
```

Checkpoint: indexer logs show upserts; agent run status moves from `queued` → `running`/`succeeded`.
