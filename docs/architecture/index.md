# Architecture overview

T-KEIR is a document-analysis and retrieval platform: NLP pipeline → Vespa
two-level index → hybrid search / RAG → optional agents, ingest, audit, and
governor. Service names and ports below come from
`deploy/compose/docker-compose.yml`. Package layout comes from `tkeir/thot/`.

See also: [Compose](../deployment/compose.md), [Deployment profiles](../deployment/index.md),
[Tools overview](../tools/tools_overview.md).

## System context

Actors and external systems that the Compose / P0 stack talks to. Identity is
Keycloak realm `tkeir` (profile `auth`). LLM / embeddings go through
`UnifiedLLMWrapper` (`PROVIDER`, often Ollama on the host). Search storage is
Vespa. WORM / object data uses MinIO when the `objectstore` profile is enabled.

```mermaid
flowchart TB
  subgraph actors [Actors]
    User[Human user / HMI]
    Dev[Developer / CLI]
    AgentClient[Agent / MCP client]
  end

  subgraph tkeir_sys [T-KEIR system]
    HMI[tkeir-hmi]
    API[tkeir-api RAG]
    Agent[tkeir-agent]
    Ingest[tkeir-ingest]
    Gov[tkeir-governor]
    Audit[tkeir-audit]
    MCP[tkeir-mcp]
  end

  subgraph external [External]
    KC[Keycloak IdP]
    Vespa[(Vespa)]
    Ollama[Ollama / LLM provider]
    MinIO[(MinIO S3)]
    PG[(PostgreSQL audit/keycloak)]
    SPIRE[SPIRE server/agent]
  end

  User --> HMI
  Dev --> API
  AgentClient --> Agent
  AgentClient --> MCP
  HMI --> API
  HMI --> KC
  API --> Vespa
  API --> Ollama
  API --> KC
  Ingest --> Vespa
  Ingest --> Ollama
  Agent --> API
  Agent --> Gov
  Agent --> SPIRE
  Audit --> PG
  Audit --> MinIO
  KC --> PG
```

## Container / service topology

Compose profiles group services (`core`, `auth`, `ingest`, `audit`, `governor`,
`objectstore`, `observability`, `mcp`, `agents`, `spire`). Host ports are the
left-hand side of each `ports:` mapping in
`deploy/compose/docker-compose.yml`.

```mermaid
flowchart LR
  subgraph core [profile core]
    vespa["vespa :8080 :19071"]
    api["tkeir-api :8090"]
    indexer[tkeir-indexer]
    hmi["tkeir-hmi :3000"]
  end
  subgraph auth [profile auth]
    kc["keycloak :8082"]
    kcdb[keycloak-db]
  end
  subgraph ingest_p [profile ingest]
    ingest["tkeir-ingest :8091"]
  end
  subgraph gov_p [profile governor]
    gov["tkeir-governor :8094"]
  end
  subgraph audit_p [profile audit]
    audit["tkeir-audit :8093"]
    adb[audit-db]
  end
  subgraph obj [profile objectstore]
    minio["minio :9000 :9001"]
  end
  subgraph obs [profile observability]
    grafana["grafana :3001"]
    prom["prometheus :9090"]
    loki["loki :3100"]
    tempo["tempo :3200"]
    otel["otel-collector :4317 :4318"]
  end
  subgraph agents_p [profile agents]
    agent["tkeir-agent :8092"]
  end
  subgraph mcp_p [profile mcp]
    mcp["tkeir-mcp :8093"]
  end
  subgraph spire_p [profile spire]
    spire_s[spire-server]
    spire_a[spire-agent]
  end

  hmi -->|HTTP| api
  hmi -->|OIDC| kc
  api -->|HTTP search/doc| vespa
  ingest -->|HTTP doc API| vespa
  agent -->|HTTP RAG| api
  agent -->|shared state| gov
  agent -.->|Workload API socket| spire_a
  audit -->|SQL| adb
  audit -->|S3| minio
  kc -->|SQL| kcdb
```

Note: Compose maps both `tkeir-audit` and `tkeir-mcp` to host port **8093**;
do not enable both profiles on the same host without remapping.

## Module dependency map

Top-level packages under `tkeir/thot/` (from package `__init__.py` layout and
import directions used by the services).

```mermaid
flowchart TB
  tools[thot.tools pipeline/search]
  action[thot.action]
  agent[thot.agent]
  audit[thot.audit]
  governor[thot.governor]
  ingest[thot.tools.ingest]
  mcp[thot.mcp]
  compose[thot.compose]
  core[thot.core]
  tasks[thot.tasks NLP/ontology]

  tools --> core
  tools --> action
  tools --> tasks
  agent --> action
  agent --> governor
  agent --> mcp
  agent --> tools
  ingest --> action
  ingest --> governor
  audit --> action
  governor --> action
  mcp --> tools
  mcp --> action
  compose --> core
  tasks --> core
```

CLIs (`tkeir/pyproject.toml` `[project.scripts]`): `tkeir-pipeline`,
`tkeir-rag`, `tkeir-index-documents`, `tkeir-ingest`, `tkeir-audit`,
`tkeir-governor`, `tkeir-agent`, `tkeir-mcp`, `tkeir-compose`,
`tkeir-init-vespa`, `tkeir-beir-eval`, `tkeir-create-annotation-resource`.

Checkpoint: `make docs-build` from the repo root builds `site/`.
