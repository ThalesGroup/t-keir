# Zero to Hero — install and use T-KEIR from dev to prod

This page is the **single didactic path** from a clean laptop to a production-ready
profile. Follow the chapters in order. Each chapter ends with a **checkpoint** so
you know you succeeded before moving on.

| Chapter | Profile | Goal | Time (rough) |
|---------|---------|------|--------------|
| [1](#1-what-you-will-build) | — | Map the journey | 2 min |
| [2](#2-prerequisites) | — | Tools on the host | 10–20 min |
| [3](#3-p0-dev-local--first-pipeline) | **P0** | Pipeline on fixtures | 15–40 min |
| [4](#4-p0-vespa-rag--hmi--agents) | **P0** | Search + HMI + **agents** + **OKF** on demo corpora | 30–65 min |
| [5](#5-p1-docker-compose-full-demo) | **P1** | Auth + audit + observability + per-user agents | 25–50 min |
| [6](#6-p2-kubernetes-dev-k3d) | **P2** | Helm umbrella on k3d | 30–60 min |
| [7](#7-p3-secure-cluster) | **P3** | Enforce + hardened path + SPIFFE agents | 45–90 min |
| [8](#8-p4-platform--evidence) | **P4** | Kubeflow + compliance packs | optional |
| [9](#9-day-2-operations) | — | Kill switch, DSR, evidence | ongoing |

Deep dives stay in sibling pages ([Installation](installation.md),
[NLP](ready_to_run.md), [Deployment](deployment/index.md)). This guide
is the narrative glue.

---

## 1. What you will build

T-KEIR turns documents into searchable, attributable knowledge:

```text
Documents → pipeline (NLP) → Vespa (streaming, per-user group) → RAG API → HMI
                ↓ ↓
         ActionRecords → audit (hot + WORM) → governor (kill / budgets)
                ↓ ↓
              Keycloak (OIDC intents → Vespa user_space)
                                                       ↓
              MCP tools ←→ Agents / workflows → templates → publish (approved)
```

Agents are a first-class feature: YAML roles, multi-agent workflows, ontology-driven
templates, and an MCP server — see [Agents](tools/agents.md), [MCP](tools/mcp.md),
[Templates](tools/templates.md). OKF exports the indexed corpus as Markdown
bundles — see [OKF](tools/okf.md) and [§4.5](#45-okf-export-and-wiki-brief-p0).

**Progressive maturity**

- **P0** — you develop and demo NLP + RAG + **agents** + **OKF** on your
  machine. Vespa is the only container; T-KEIR tools (`pipeline`, `ingest`,
  `rag`, `agent`, `okf`, HMI) run on the host. Streaming group **`dev@tkeir`**
  (no Keycloak required) — both OSINT and enterprise demo docs share that space.
- **P1** — you demo the full stack in Compose (local image registry `local/…`,
  Keycloak, ingest, audit, Grafana, optional `mcp` / `agents`). Each Keycloak
  user gets an isolated Vespa corpus; agents search only that user’s space
  (OSINT → `demo-user`, enterprise → `demo-admin`).
- **P2** — you install the same stack with Helm on a local Kubernetes (k3d),
  including optional agent / MCP charts when enabled in values.
- **P3** — you harden (auth on, governor enforce, network policies). Agent
  workloads use SPIFFE; enable
  Compose profile `spire` with `agents`.
- **P4** — you add Kubeflow lineage and automated compliance evidence.

---

## 2. Prerequisites

### Host tools

| Tool | Why | Check |
|------|-----|-------|
| Git | Clone the repo | `git --version` |
| [uv](https://docs.astral.sh/uv/) | Python 3.11 env | `uv --version` |
| Make | All entrypoints | `make --version` |
| Docker Desktop / Colima / Engine | Vespa + Compose | `docker info` |
| Node.js 20+ | HMI (`tkeir-hmi`) | `node -v` |
| (Optional) Ollama | Local LLM / embeddings on macOS | `ollama list` |

**macOS tip:** prefer Ollama on the host (Metal) and point Compose / RAG at
`http://host.docker.internal:11434`. See [macOS notes](deployment/macos.md).

### Alternative: Dev Container

If you want a pre-wired IDE environment:

1. Open the repo in VS Code / Cursor.
2. Reopen in Container (`.devcontainer/`).
3. Continue from [§3](#3-p0-dev-local--first-pipeline) inside the container.

Details: [Dev Container](devcontainer.md).

### Clone

```bash
git clone https://github.com/ThalesGroup/t-keir.git
cd t-keir
```

**Checkpoint:** `ls Makefile tkeir/thot tkeir-hmi deploy` succeeds.

---

## 3. P0 `dev-local` — first pipeline

### 3.1 Install Python deps and spaCy models

From the **repository root**:

```bash
make setup
```

This creates the `tkeir` uv environment (Python 3.11), installs the package, and
pulls spaCy models used by the pipeline.

**Checkpoint:**

```bash
cd tkeir && uv run --python 3.11 python -c "import thot; print(thot.__version__)"
```

### 3.2 Run the bundled quickstart

```bash
make quickstart
```

What happens: `tkeir-pipeline` analyzes text under
`tkeir/tests/fixtures/test-raw/` (no Vespa indexing) and writes JSON under
`output/quickstart/`.

**Checkpoint:** `ls output/quickstart/raw/*.json | head` shows analyzed documents.

### 3.3 Analyse *your* documents

```bash
make pipeline \
  PIPELINE_INPUT=/path/to/your/docs \
  PIPELINE_OUTPUT=$PWD/workspace/tmp/my-run \
  PIPELINE_TYPE=auto
```

- Use `-t auto` / `PIPELINE_TYPE=auto` for PDF and Office.
- Use `raw` only for plain text.

More detail: [NLP](ready_to_run.md).

**Checkpoint:** Your output directory contains `*.json` with `content_tokens` /
NER fields.

### 3.4 Demo datasets (already versioned)

OSINT and enterprise demo data ship in the repo under `datasets/` — you do
**not** need `make datasets` for the Zero-to-Hero path.

| Dataset | Theme | Default user | Versioned artifacts |
|---------|-------|--------------|---------------------|
| `datasets/osint/` | NATO C4ISR OSINT (SITREP, INTSUM, OPORD…) | `demo-user` | `VERSION`, `corpus.jsonl`, `business_ontology.yaml`, C2SIM ontologies |
| `datasets/enterprise/` | AcmeSystems (+ optional EnterpriseRAG slice) | `demo-admin` | `VERSION`, `corpus.jsonl`, `business_ontology.yaml` |

**Checkpoint:** `cat datasets/osint/VERSION` and
`cat datasets/enterprise/VERSION` (currently `1.1.0`);
`ls datasets/osint/corpus.jsonl datasets/enterprise/corpus.jsonl
datasets/osint/ontologies/*.owl` all exist.

Optional — regenerate or re-download only if you are maintaining the datasets
themselves (see [Datasets](tools/datasets.md)):

```bash
make datasets                 # refresh generate + best-effort download
make datasets DATASETS_DOWNLOAD=0
```

### 3.5 Ingest the datasets (P0 — host tools)

P0 has **no containerization of T-KEIR tools**. Only Vespa runs in Docker;
pipeline, ingest, RAG, agent, and the HMI run on the host via `uv` / `npm`.

Without Keycloak, both datasets land in the shared `dev@tkeir` space.
`make datasets-ingest` runs **two passes**: OSINT with client-side
`--ontology-dir datasets/osint/ontologies` (bytes uploaded as `ontology_file`
parts), then enterprise without ontologies.

```bash
# Terminal A — Vespa + host ingest API (:8091)
make bootstrap
make ingest # serializes NLP (INGEST_MAX_CONCURRENCY=1); avoid OOM

# Terminal B — push versioned datasets into dev@tkeir
make datasets-ingest
```

Debug (stop on first failure):

```bash
make ingest STOP_ON_FAILED=1          # terminal A
make datasets-ingest STOP_ON_FAILED=1 # terminal B
```

One-shot ingest (API must already listen on `:8091`):

```bash
make datasets-ingest
```

If `:8091` is down, start `make ingest` (P0) or Compose from P1:

```bash
make images
make compose-up PROFILES=core,ingest
make datasets-ingest
```

Small slice only (host fallback is slow for the full set):

```bash
make datasets-ingest INGEST_FLAGS='--topics situational_awareness --formats txt --force-fallback'
```

**Checkpoint:** `datasets/ingest_osint.json` and
`datasets/ingest_enterprise.json` exist with `"failed": 0`.
After [§4.2](#42-start-the-rag-api):
`make rag-query RAG_QUERY="SITREP Objective ALPHA"` returns chunk hits.

---
## 4. P0 — Vespa RAG + HMI + agents

Still **host-native** for T-KEIR: `make rag`, `make agent`, `make okf`, and
`cd tkeir-hmi && npm run dev`. Vespa runs in Docker (`make bootstrap`).
Streaming mode: documents live in a *user space* (Vespa group). Without
Keycloak, everything uses the fixed principal **`dev@tkeir`** — so OSINT and
enterprise demo data are both visible to RAG, agents, and OKF in P0.

| Mode | Vespa `user_space` / `streaming.groupname` |
|------|--------------------------------------------|
| P0 / auth off / CLI (`make index`, `make rag`) | `dev@tkeir` (override with `VESPA_USER_SPACE`) |
| Keycloak signed-in (P1+) | `preferred_username` → `email` → `sub` |

Details: [Vespa RAG — user space](tools/vespa_rag.md#user-space-streaming-group).

### 4.1 Bootstrap Vespa and index fixtures

```bash
# Optional: explicit local space (default is already dev@tkeir)
export VESPA_USER_SPACE=dev@tkeir

make bootstrap # start Vespa + deploy streaming schemas
make index-fixtures # build pipeline JSON under tkeir/tests/indexing/output if needed
make index # feed into g=dev@tkeir
```

**Checkpoint:** Vespa responds on `http://localhost:8080` (config on `19071`).
After a mode change (indexed → streaming), wipe data first:
`bash vespa/clean_db.sh` then re-run `make bootstrap` and `make index`.

### 4.2 Start the RAG API

```bash
make rag
# other terminal:
make rag-query RAG_QUERY="What is T-KEIR?"
```

API listens on **:8090**. Queries without a Bearer token search **`dev@tkeir`**.
Each answer carries `X-Correlation-Id` for audit later.

For the richer demo datasets ([§3.4](#34-demo-datasets-already-versioned) /
[§3.5](#35-ingest-the-datasets-p0--host-tools)), keep ingest and RAG on the
**host** (no tkeir containers):

```bash
make bootstrap
make ingest # terminal A — :8091
# other terminal:
make datasets-ingest # versioned datasets/ already in the repo
make rag # :8090
make rag-query RAG_QUERY="SITREP Objective ALPHA" # OSINT hits
make rag-query RAG_QUERY="AcmeSystems Project ATLAS" # Enterprise hits (same space in P0)
```

With P1 Compose and the two users loaded (§5.5), the same queries return
results only for the user who owns the matching corpus.

### 4.3 Open the HMI

```bash
cd tkeir-hmi && npm install && npm run dev
```

Browse **http://localhost:3000**. For local P0 without login, keep
`AUTH_ENABLED=false` (default outside Compose) — the UI hits the same
`dev@tkeir` corpus.

**Checkpoint:** A query in the HMI returns an answer and shows a correlation id.

### 4.4 Agents on OSINT and enterprise demo data (P0)

After [§3.5](#35-ingest-the-datasets-p0--host-tools) and [§4.2](#42-start-the-rag-api),
run grounded agents against the shared `dev@tkeir` index. Agents call
`search` / `rag_query` / `ontology_query` / `document_get` (and optional
workflows) over that space — claims must cite chunk or document ids.

**Prerequisites**

| Need | Why |
|------|-----|
| Corpora ingested | OSINT + enterprise under `dev@tkeir` |
| `make rag` on **:8090** | Agent tools talk to the RAG API |
| Local LLM (e.g. Ollama) | `UnifiedLLMWrapper` drives the agent loop |
| `make agent` on **:8092** | `tkeir-agent` HTTP service |

```bash
# Ensure Ollama (or another PROVIDER) is reachable — see §2
# export PROVIDER=ollama LLM_MODEL=mistral-nemo

# Terminal A — RAG (if not already up)
make rag

# Terminal B — agent service
make agent
```

**OSINT (NATO C4ISR corpus)** — researcher single-shot and multi-agent brief:

```bash
make agent-run \
  GOAL="Summarize SITREP findings about Objective ALPHA from the indexed corpus" \
  AGENT=researcher

make workflow-run \
  GOAL="Produce an OSINT content brief on Objective ALPHA and related units" \
  WORKFLOW=content_brief \
  TOPIC="Objective ALPHA"
```

Polling waits up to ~6 minutes for workflows (`WORKFLOW_POLL_ATTEMPTS=180` ×
`AGENT_POLL_SECONDS=2`). If Make times out, the run may still finish — check
`curl -s http://localhost:8092/agent/runs/<run_id> | jq '{status:.run.status,compose_result}'`.

Ontology-aware tools benefit from the C2SIM/C4ISR ontologies uploaded with
OSINT ingest (`DATASETS_ONTOLOGY_DIR` / `ontology_file` parts).

**Enterprise (AcmeSystems corpus)** — same host, same `dev@tkeir` space:

```bash
make agent-run \
  GOAL="What is the status of AcmeSystems Project ATLAS in the indexed docs?" \
  AGENT=researcher

make workflow-run \
  GOAL="Profile Project ATLAS for leadership: risks, owners, and open actions" \
  WORKFLOW=content_brief \
  TOPIC="Project ATLAS"
```

**HMI monitor**

```bash
export AGENT_URL=http://localhost:8092
# with tkeir-hmi already running (§4.3)
open http://localhost:3000/agents # or browse manually
```

Start `content_brief` from the UI, poll handoffs / compose preview, and (when
governor allows) publish. Details: [Agents](tools/agents.md).

**Checkpoint:** `make agent-run` for an OSINT goal and an enterprise goal both
reach `status=succeeded` (or show grounded `findings` with `chunk_ids`).
Workflow runs return `handoffs` + `compose_result`. In P0 both themes hit the
same streaming group; isolation comes in [§5.5](#55-per-user-and-per-topic-dataset-segregation-p1) /
[§5.6](#56-agents-on-osint-vs-enterprise-p1).

### 4.5 OKF export and wiki brief (P0)

OKF (Open Knowledge Format) turns the indexed `dev@tkeir` corpus into a
**directory of Markdown concepts** you can browse, download, or enrich with
agents. In P0 everything stays host-native — no Compose `okf` profile required.
Details: [OKF](tools/okf.md).

**Prerequisites:** corpora ingested ([§3.5](#35-ingest-the-datasets-p0--host-tools)),
`make rag` on **:8090** ([§4.2](#42-start-the-rag-api)). For the wiki-brief
workflow, also run `make agent` ([§4.4](#44-agents-on-osint-and-enterprise-demo-data-p0)).

**1. Query-scoped export (CLI)** — RAG selects the documents; T-KEIR writes a
bundle under `.tkeir-okf/`:

```bash
# Terminal A — RAG must be up
make rag

# Terminal B — scoped OKF export from the OSINT theme
make okf-export \
  USER_SPACE=dev@tkeir \
  QUERY="SITREP Objective ALPHA"

# Or a static walk of the first N parent docs (no query)
make okf-export USER_SPACE=dev@tkeir OKF_MAX_DOCS=20
```

**Checkpoint:** `.tkeir-okf/<bundle_id>/index.md` exists. A scoped export also
has `query_context.md` with the query and linked concepts. Open a concept file
under `concepts/` — frontmatter includes `type` plus T-KEIR `tkeir_*` fields.

**2. HTTP API + HMI browser** — optional when you want list/download from the UI:

```bash
# Terminal C — OKF service (:8094); keep RAG on :8090
make okf

# List bundles for the default caller space
make okf-bundle-ls

# With HMI already running (§4.3)
open http://localhost:3000/okf
```

From `/okf`, trigger a query-scoped export, open `index.md` / concepts, or
download the `.tar.gz`.

**3. Curated wiki brief** — `okf_wiki_brief` scopes a bundle, runs
`okf_curator` enrichments, then composes a `synthesis_note`:

```bash
# RAG (:8090) + agent (:8092) already up from §4.4
make okf-workflow \
  GOAL="Produce an OKF knowledge brief on Objective ALPHA" \
  TOPIC="Objective ALPHA"
```

**Checkpoint:** the workflow run reaches `status=succeeded` with
`compose_result`; the curated bundle under `.tkeir-okf/` shows enrichments in
concept notes / `log.md`. Enterprise theme works the same with
`TOPIC="Project ATLAS"` and a matching `GOAL`.

---

## 5. P1 Docker Compose — full demo

Compose packages the same services as containers. Images default to the
**local** registry (`IMAGE_REGISTRY=local` → `local/tkeir-api:…`). Build
before the first `compose-up` (Compose will not pull from GHCR unless you set
`IMAGE_REGISTRY=ghcr.io/thalesgroup/t-keir`).

```bash
cp deploy/compose/.env.example deploy/compose/.env # IMAGE_REGISTRY=local
make images
```

With **`auth`**, each Keycloak user owns a separate Vespa streaming group
(HMI forwards the access token; API/ingest resolve `user_space` from the JWT).

### 5.1 Env file

```bash
cp deploy/compose/.env.example deploy/compose/.env
# IMAGE_REGISTRY=local # default — local Docker daemon tags
# VESPA_USER_SPACE=dev@tkeir # CLI / auth-off fallback only
# edit secrets if you expose the stack beyond localhost
```

### 5.2 Start profiles

Minimal authenticated demo:

```bash
make compose-up PROFILES=core,auth
```

Industrial demo (recommended once P0 works):

```bash
make compose-up PROFILES=core,auth,ingest,audit,governor,observability,objectstore
```

Full demo **with agents + MCP** (after images are built):

```bash
make compose-up PROFILES=core,auth,ingest,audit,governor,observability,objectstore,mcp,agents
```

| Profile | What you get | Ports |
|---------|--------------|-------|
| `core` | Vespa, API, indexer, HMI | 3000, 8080, 8090 |
| `auth` | Keycloak | **8082** |
| `ingest` | Document push API | 8091 |
| `audit` | Hot store + WORM | 8093 |
| `governor` | Kill / budgets / tokens | 8094 |
| `observability` | Grafana, Prom, Loki, Tempo, OTel | Grafana **3001** |
| `objectstore` | MinIO (WORM buckets) | 9000 / 9001 |
| `mcp` | MCP tool server | (compose network / published port) |
| `agents` | `tkeir-agent` | **8092** |

Guide: [Compose (P1)](deployment/compose.md).

### 5.3 Smoke test

```bash
make compose-smoke
# optional RAG assertion (auth-off / env user space unless a token is set):
COMPOSE_SMOKE_RAG=1 make compose-smoke
```

### 5.4 Log in (Keycloak) — per-user Vespa space

| User | Password | Role | Typical Vespa group |
|------|----------|------|---------------------|
| `demo-user` | `demo-user` | user | `demo-user` (`preferred_username`) |
| `demo-auditor` | `demo-auditor` | auditor | `demo-auditor` |
| `demo-admin` | `demo-admin` | admin | `demo-admin` |

Emails in the realm are `*@tkeir` (used only if `preferred_username` is absent).

HMI with `AUTH_ENABLED=true` redirects to Keycloak and attaches
`Authorization: Bearer <access_token>` on `/api/*` proxies. The RAG API then
sets `streaming.groupname` from that token — **demo-user cannot see
demo-admin’s indexed docs**.

**Try it**

1. Sign in as `demo-user`, ingest or index into that session (or call ingest
   with that user’s token).
2. Ask a question in the HMI — hits come from `g=demo-user`.
3. Sign out, sign in as `demo-admin` — empty / different corpus unless you
   indexed there too.

Admin panel: **http://localhost:3000/admin** (auditor/admin).

**Checkpoint:** `compose-smoke` PASS; Grafana at http://localhost:3001 (if
observability profile is up); two Keycloak users see **isolated** search
results when they hold different corpora.

### 5.5 Per-user and per-topic dataset segregation (P1)

Copy/paste — bring up auth + ingest, then load each dataset into its owner’s
Vespa group:

```bash
make compose-up PROFILES=core,auth,ingest
make compose-smoke

# OSINT → demo-user streaming group
make datasets-ingest-user

# Enterprise → demo-admin streaming group
make datasets-ingest-admin
```

Prerequisite: `make images` so Compose finds `local/tkeir-*:…` (see §5 intro).

Topic-filtered OSINT (optional):

```bash
python3 tools/datasets/ingest_dataset.py \
  --datasets-dir datasets \
  --dataset osint --topics intelligence \
  --username demo-user --password demo-user \
  --token-url http://localhost:8082/realms/tkeir/protocol/openid-connect/token
```

**Prefer the web interface?** HMI drag-and-drop and curl with real filenames:

```bash
make datasets-ingest-web
```

**Verifying isolation**

Sign in as `demo-user` → query *"AcmeSystems Project ATLAS"* → 0 results.
Sign in as `demo-admin` → query *"SITREP Objective ALPHA"* → 0 results.

From the CLI:

```bash
# demo-user cannot see enterprise docs
TOKEN_U=$(python3 tools/datasets/ingest_dataset.py --print-token \
  --username demo-user --password demo-user \
  --token-url http://localhost:8082/realms/tkeir/protocol/openid-connect/token)
curl -s -H "Authorization: Bearer $TOKEN_U" \
  "http://localhost:8090/rag/query?q=AcmeSystems+Project+ATLAS" \
  | python3 -c "import sys,json; print('hits:', len(json.load(sys.stdin).get('chunks',[])))"
# → hits: 0
```

**Checkpoint:** `workspace/ingest_user.json` and `workspace/ingest_admin.json` both
show `"failed": 0`; cross-user isolation queries return 0 hits.

### 5.6 Agents on OSINT vs enterprise (P1)

With [§5.5](#55-per-user-and-per-topic-dataset-segregation-p1) loaded and the
`agents` Compose profile up, agents inherit **`user_space` from the Bearer
token** (tool args cannot override it). Run OSINT goals as `demo-user` and
enterprise goals as `demo-admin`.

```bash
# Ensure agents (+ RAG) are in the stack
make compose-up PROFILES=core,auth,ingest,mcp,agents
# corpora already in demo-user / demo-admin (§5.5)

TOKEN_U=$(python3 tools/datasets/ingest_dataset.py --print-token \
  --username demo-user --password demo-user \
  --token-url http://localhost:8082/realms/tkeir/protocol/openid-connect/token)
TOKEN_A=$(python3 tools/datasets/ingest_dataset.py --print-token \
  --username demo-admin --password demo-admin \
  --token-url http://localhost:8082/realms/tkeir/protocol/openid-connect/token)
```

**OSINT agent** (`demo-user` → NATO corpus only):

```bash
curl -fsS http://localhost:8092/agent/runs \
  -H "Authorization: Bearer $TOKEN_U" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-Id: $(python3 -c 'import secrets; print(secrets.token_hex(16))')" \
  -d '{"agent":"researcher","goal":"Summarize SITREP findings about Objective ALPHA"}' \
  | jq .
# poll: GET /agent/runs/{run_id} with the same Bearer
```

**Enterprise agent** (`demo-admin` → AcmeSystems corpus only):

```bash
curl -fsS http://localhost:8092/agent/runs \
  -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-Id: $(python3 -c 'import secrets; print(secrets.token_hex(16))')" \
  -d '{"agent":"researcher","goal":"What is the status of AcmeSystems Project ATLAS?"}' \
  | jq .
```

**Multi-agent briefs** (same isolation):

```bash
# OSINT brief as demo-user
curl -fsS http://localhost:8092/agent/runs \
  -H "Authorization: Bearer $TOKEN_U" \
  -H "Content-Type: application/json" \
  -d '{"workflow":"content_brief","goal":"OSINT brief on Objective ALPHA","params":{"topic":"Objective ALPHA"}}' \
  | jq .

# Enterprise brief as demo-admin
curl -fsS http://localhost:8092/agent/runs \
  -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -d '{"workflow":"content_brief","goal":"Leadership brief on Project ATLAS","params":{"topic":"Project ATLAS"}}' \
  | jq .
```

**Cross-tenant check:** as `demo-user`, an enterprise-only goal should finish
with empty / weak grounded findings (no ATLAS chunks), not with admin docs.
Sign in at **http://localhost:3000/agents** as each user to confirm the UI
run monitor respects the session token.

Host shortcuts `make agent-run` / `make workflow-run` omit Keycloak and use
`VESPA_USER_SPACE` / auth-off defaults — prefer the Bearer curls above for the
P1 isolation demo.

**Checkpoint:** OSINT run as `demo-user` cites SITREP / Objective ALPHA chunks;
enterprise run as `demo-admin` cites Project ATLAS; the swapped goals do not
surface the other corpus.

---

## 6. P2 Kubernetes dev (k3d)

### 6.1 Create a local cluster

```bash
make k3d-up
```

### 6.2 Install the umbrella chart

```bash
make helm-deps
make cluster-install PROFILE=k8s-dev
# or:
make cluster-plan # detect what the cluster already has
```

Values: `deploy/charts/tkeir/values-dev.yaml`.  
Guide: [Kubernetes (P2)](deployment/k8s.md).

### 6.3 Optional Keycloak on cluster

```bash
helm upgrade --install tkeir deploy/charts/tkeir \
  -f deploy/charts/tkeir/values-dev.yaml \
  --set keycloak.enabled=true
```

With Keycloak enabled, HMI/API behave like Compose P1: JWT → Vespa
`user_space`. Without it, pods use `VESPA_USER_SPACE=dev@tkeir` from
`values-dev.yaml`.

Token exchange notes: [Token exchange](deployment/token-exchange.md).

### 6.4 Agents on demo datasets (P2)

Same agent goals as [§4.4](#44-agents-on-osint-and-enterprise-demo-data-p0) /
[§5.6](#56-agents-on-osint-vs-enterprise-p1), pointed at the cluster RAG and
agent Services (port-forward or ingress). With Keycloak on cluster, reuse the
`demo-user` / `demo-admin` Bearer pattern so OSINT and enterprise stay isolated.
Without Keycloak, agents use `VESPA_USER_SPACE=dev@tkeir` from
`values-dev.yaml` (both datasets share one space, like P0).

**Checkpoint:** `kubectl -n tkeir get pods` shows Running; `helm test` / chart
smoke succeeds when configured. Optional: one OSINT and one enterprise agent
run against the in-cluster `tkeir-agent` Service succeed.

---

## 7. P3 Secure cluster

P3 turns on **governor enforce**, **audit**, and **auth**. When agents are
enabled, SPIRE/SPIFFE identity is required for mastering.

### Path A — Linux / cloud K3s

```bash
# on server nodes
bash deploy/k3s/install-server.sh
# on agents
bash deploy/k3s/install-agent.sh
make cilium-install # when ready for eBPF networking
make cluster-install PROFILE=k8s-secure
make k3s-check # kube-bench style checks when available
```

### Path B — macOS via Lima

```bash
make lima-k3s-up
make cluster-install PROFILE=k8s-secure
```

Guides: [Secure cluster](deployment/k8s-secure.md), [macOS](deployment/macos.md),
[SPIRE / SPIFFE](deployment/spire.md).

### 7.1 Agents under enforce (P3)

Repeat the [§5.6](#56-agents-on-osint-vs-enterprise-p1) OSINT / enterprise
runs with governor **`enforce`** and SPIFFE on the agent workload:

- Budgets (`llm_tokens`, `tool_calls`, `wall_seconds`) throttle / block runs.
- Kill scope: `make governor-kill SCOPE=agents ACTIVE=true`.
- Publish from the HMI requires ApprovalQueue approval (`/admin`).
- ActionRecords carry `actor.type=agent` and `actor.spiffe_id`.

Demo goals stay the same (Objective ALPHA as `demo-user`, Project ATLAS as
`demo-admin`); only governance and identity are stricter.

**Checkpoint:** Governor mode is `enforce`; unauthenticated privileged calls
fail; kill switch works (`make governor-kill` / runbook); an agent run under
`demo-user` / `demo-admin` still grounds on the correct corpus or is blocked
cleanly by budget / kill / approval.

---

## 8. P4 Platform + evidence

```bash
make cluster-install PROFILE=platform
make kubeflow-install # when cluster ready
make kubeflow-register-models # stub registry entries
make lineage-report DOC=<sha256>
make annex-iv
make audit-evidence
make audit-compliance # OPA EU article audit → reports/compliance/eu-audit/
```

Compliance mappings (engineering, **not legal advice**):
[Compliance overview](compliance/index.md) ·
[EU Compliance OPA Audit](compliance/eu-audit.md) (category gates,
`NOT_MANDATORY`, full article catalogues).

**Checkpoint:** Evidence pack exists under `reports/evidence/`, Annex IV under
`reports/compliance/annex-iv/`, and (when `opa` is installed) an HTML report
under `reports/compliance/eu-audit/<git-describe>/`.

---

## 9. Day-2 operations

| Task | Command / doc |
|------|----------------|
| Kill a scope | [Kill-switch runbook](runbooks/kill-switch.md) |
| Incident stub | `tkeir-audit incident` → [Incident](runbooks/incident.md) |
| Index rollback | [Rollback](runbooks/rollback.md) |
| GDPR forget | `tkeir-audit forget --subject …` → [DSR](runbooks/dsr.md) |
| Verify WORM | `make audit-verify` |
| Seal a secret | `make seal` |

---

## 10. Code documentation (Google style)

Public helpers under `thot/` use **Google-style** docstrings. When a function
includes a runnable example, it lives in an `Example:` block with `>>>` prompts.
Those examples are **executed in CI**:

```bash
cd tkeir
uv run pytest tests/unittests/TestAllDocExamples.py -q
uv run pytest tests/unittests/TestDocExampleCoverage.py -q
```

Catalog: [Tools API reference](tools/api_reference.md).

### Architecture reference

Formal diagrams and the typed class/schema reference live in the
[Architecture](architecture/index.md) section. They are generated from the
source during the same CI run that checks docstring examples:

```bash
make docs-build
```

### Complexity, coverage, and licence gates

`make ci` publishes the following on the
[Code quality dashboard](quality/index.md):

- **Test coverage** — `make coverage` runs the scoped suite
  (`CoverageFast.sh`) and fails below `COVERAGE_FAIL_UNDER` (default 90%).
  Totals land in `reports/quality/coverage_*.*`.
- **Cyclomatic complexity** — `make complexity` / `make complexity-report`
  runs Radon on `thot/` and fails if the average CC exceeds 7.0 (grade B) or
  any function reaches grade D (CC > 20).
- **Dependency licences** — `make pip-licenses` inventories locked
  dependencies. Copyleft strings require a review entry in
  `compliance/licenses-allowlist.txt` before merge (runtime policy remains
  `make liccheck`).

Regenerate the dashboard after any refactoring or coverage pass:

```bash
make coverage # refreshes reports/quality/coverage_*.*
make quality-docs # writes docs/quality/index.md from latest reports
make docs-build # rebuilds the full MkDocs site
```

---

## Where to go next

| If you want… | Open |
|--------------|------|
| Architecture diagrams & data model | [Architecture](architecture/index.md) |
| Code quality (coverage + CC + licences) | [Quality dashboard](quality/index.md) |
| Pipeline stages | [Tools overview](tools/tools_overview.md) |
| Vespa schema / RAG | [Vespa RAG](tools/vespa_rag.md) |
| MCP / agents / templates / OKF | [MCP](tools/mcp.md), [Agents](tools/agents.md), [Templates](tools/templates.md), [OKF](tools/okf.md) |
| Ingest API | [Ingestion](deployment/ingest.md) |
| Audit / WORM | [Audit store](deployment/audit.md) |
| Governor | [Governor](deployment/governor.md) |
| Security model | [Security](security.md) |
| EU compliance OPA | [EU Compliance OPA Audit](compliance/eu-audit.md) |

```bash
make help # every Make target with a one-line description
```
