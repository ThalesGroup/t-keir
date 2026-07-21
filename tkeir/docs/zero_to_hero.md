# Zero to Hero — install and use T-KEIR from dev to prod

This page is the **single didactic path** from a clean laptop to a production-ready
profile. Follow the chapters in order. Each chapter ends with a **checkpoint** so
you know you succeeded before moving on.

| Chapter | Profile | Goal | Time (rough) |
|---------|---------|------|--------------|
| [1](#1-what-you-will-build) | — | Map the journey | 2 min |
| [2](#2-prerequisites) | — | Tools on the host | 10–20 min |
| [3](#3-p0-dev-local--first-pipeline) | **P0** | Pipeline on fixtures | 15–40 min |
| [4](#4-p0-vespa-rag--hmi) | **P0** | Search + web UI | 20–45 min |
| [5](#5-p1-docker-compose-full-demo) | **P1** | Auth + audit + observability | 20–40 min |
| [6](#6-p2-kubernetes-dev-k3d) | **P2** | Helm umbrella on k3d | 30–60 min |
| [7](#7-p3-secure-cluster) | **P3** | Enforce + hardened path | 45–90 min |
| [8](#8-p4-platform--evidence) | **P4** | Kubeflow + compliance packs | optional |
| [9](#9-day-2-operations) | — | Kill switch, DSR, evidence | ongoing |

Deep dives stay in sibling pages ([Installation](installation.md),
[Quickstart](ready_to_run.md), [Deployment](deployment/index.md)). This guide
is the narrative glue.

---

## 1. What you will build

T-KEIR turns documents into searchable, attributable knowledge:

```text
Documents → pipeline (NLP) → Vespa (streaming, per-user group) → RAG API → HMI
                ↓                                      ↓
         ActionRecords → audit (hot + WORM) → governor (kill / budgets)
                ↓                                      ↓
              Keycloak (OIDC intents → Vespa user_space)
                                                       ↓
              MCP tools ←→ Agents / workflows → templates → publish (approved)
```

Agents are a first-class feature: YAML roles, multi-agent workflows, ontology-driven
templates, and an MCP server — see [Agents](tools/agents.md), [MCP](tools/mcp.md),
[Templates](tools/templates.md).

**Progressive maturity**

- **P0** — you develop and demo NLP + RAG on your machine. Vespa uses streaming
  mode with the shared local group **`dev@tkeir`** (no Keycloak required).
- **P1** — you demo the full stack in Compose (Keycloak, ingest, audit, Grafana).
  Each Keycloak user gets an isolated Vespa corpus (`preferred_username` / email).
- **P2** — you install the same stack with Helm on a local Kubernetes (k3d).
- **P3** — you harden (auth on, governor enforce, network policies). Agent
  workloads use SPIFFE ([ADR-0008](adr/0008-spire-agent-identity.md)); enable
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

More detail: [Quickstart](ready_to_run.md).

**Checkpoint:** Your output directory contains `*.json` with `content_tokens` /
NER fields.

### 3.4 Generate the demo corpora (recommended)

The fixture files cover only a minimal smoke test. For a realistic demo across
two independent themes, seven formats, and two languages, run the corpus generator:

```bash
make corpus
```

This generates two offline corpora under `workspace/`:

| Corpus | Theme | Default user | Documents | Formats |
|--------|-------|-------------|-----------|---------|
| `corpus_nato/` | NATO C4ISR OSINT (SITREP, INTSUM, OPORD…) | `demo-user` | 1 500 | txt md html json csv pdf docx |
| `corpus_enterprise/` | AcmeSystems internal docs (specs, HR, finance…) | `demo-admin` | 500 | txt md html pdf docx json csv |

Each document carries a `user_space` and a `topic_id` (sub-folder within the
corpus). Six NATO C2SIM/C4ISR ontologies are written to
`workspace/corpus_nato/ontologies/` and are ready for the ontology-driven
template phase ([Templates](tools/templates.md)).

Online? Fetch the official SISO C2SIM ontology artifacts
(OpenC2SIM/C2SIMArtifacts on GitHub) and a slice of the EnterpriseRAG-Bench
dataset (onyx-dot-app/EnterpriseRAG-Bench on HuggingFace, MIT license):

```bash
make corpus-download
```

The build remains fully functional offline: embedded generators produce all
1 500 + 500 documents without any network access.

**Checkpoint:** `ls workspace/corpus_nato/manifest.json
workspace/corpus_enterprise/manifest.json
workspace/corpus_nato/ontologies/*.owl` all exist.
`python3 -c "import json; m=json.load(open('workspace/corpus_nato/manifest.json'));
print(m['count_generated'])"` prints `1500`.

### 3.5 Ingest the corpora (P0 — offline)

Without Keycloak, both corpora land in the shared `dev@tkeir` space. The
`--fallback-index` flag automatically uses `make index` when `tkeir-ingest`
is not running:

```bash
make corpus-ingest
```

Or generate and ingest in one command:

```bash
make corpus-demo
```

**Checkpoint:** `workspace/ingest_report.json` exists and shows `"failed": 0`.
`make rag-query RAG_QUERY="SITREP Objective ALPHA"` returns chunk hits.

---

## 4. P0 — Vespa RAG + HMI

Vespa runs in **streaming mode**: documents live in a *user space* (Vespa
group). Without Keycloak, everything uses the fixed principal **`dev@tkeir`**.

| Mode | Vespa `user_space` / `streaming.groupname` |
|------|--------------------------------------------|
| P0 / auth off / CLI (`make index`, `make rag`) | `dev@tkeir` (override with `VESPA_USER_SPACE`) |
| Keycloak signed-in (P1+) | `preferred_username` → `email` → `sub` |

Details: [Vespa RAG — user space](tools/vespa_rag.md#user-space-streaming-group).

### 4.1 Bootstrap Vespa and index fixtures

```bash
# Optional: explicit local space (default is already dev@tkeir)
export VESPA_USER_SPACE=dev@tkeir

make bootstrap      # start Vespa + deploy streaming schemas
make index-fixtures # build pipeline JSON under tkeir/tests/indexing/output if needed
make index          # feed into g=dev@tkeir
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

For the richer demo corpus (§3.4), substitute the fixture index:

```bash
make corpus-demo                                     # generate + ingest (P0)
make rag-query RAG_QUERY="SITREP Objective ALPHA"   # OSINT hits
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

---

## 5. P1 Docker Compose — full demo

Compose packages the same services with optional Keycloak, ingest, audit,
governor, Grafana, and MinIO. With **`auth`**, each Keycloak user owns a
separate Vespa streaming group (HMI forwards the access token; API/ingest
resolve `user_space` from the JWT).

### 5.1 Env file

```bash
cp deploy/compose/.env.example deploy/compose/.env
# VESPA_USER_SPACE=dev@tkeir  # CLI / auth-off fallback only
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

| Profile | What you get | Ports |
|---------|--------------|-------|
| `core` | Vespa, API, indexer, HMI | 3000, 8080, 8090 |
| `auth` | Keycloak | **8082** |
| `ingest` | Document push API | 8091 |
| `audit` | Hot store + WORM | 8093 |
| `governor` | Kill / budgets / tokens | 8094 |
| `observability` | Grafana, Prom, Loki, Tempo, OTel | Grafana **3001** |
| `objectstore` | MinIO (WORM buckets) | 9000 / 9001 |

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

### 5.5 Per-user and per-topic corpus segregation (P1)

With Keycloak running (`make compose-up PROFILES=core,auth,ingest`), each
Keycloak user owns a completely isolated Vespa streaming group. The corpus
generator assigns each document to a target user; the ingest script routes
it there automatically.

**Ingest the OSINT corpus as demo-user:**

```bash
make corpus-ingest-user

# or with a specific topic only:
python3 tools/corpus/ingest_corpus.py \
  --corpus-dir workspace \
  --corpus osint --topics intelligence \
  --username demo-user --password demo-user \
  --token-url http://localhost:8082/realms/tkeir/protocol/openid-connect/token
```

**Ingest the Enterprise corpus as demo-admin:**

```bash
make corpus-ingest-admin
```

**Prefer the web interface?** Get the full step-by-step guide (HMI
drag-and-drop and curl variants with real filenames):

```bash
make corpus-ingest-web
```

**Verifying isolation**

Sign in as `demo-user` → query *"AcmeSystems Project ATLAS"* → 0 results.
Sign in as `demo-admin` → query *"SITREP Objective ALPHA"* → 0 results.

From the CLI:

```bash
# demo-user cannot see enterprise docs
TOKEN_U=$(python3 tools/corpus/ingest_corpus.py --print-token \
  --username demo-user --password demo-user \
  --token-url http://localhost:8082/realms/tkeir/protocol/openid-connect/token)
curl -s -H "Authorization: Bearer $TOKEN_U" \
  "http://localhost:8090/rag/query?q=AcmeSystems+Project+ATLAS" \
  | python3 -c "import sys,json; print('hits:', len(json.load(sys.stdin).get('chunks',[])))"
# → hits: 0
```

**Checkpoint:** `workspace/ingest_user.json` and `workspace/ingest_admin.json` both
show `"failed": 0`; cross-user isolation queries return 0 hits.

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
make cluster-plan   # detect what the cluster already has
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

**Checkpoint:** `kubectl -n tkeir get pods` shows Running; `helm test` / chart
smoke succeeds when configured.

---

## 7. P3 Secure cluster

P3 turns on **governor enforce**, **audit**, and **auth**. When agents are
enabled, SPIRE/SPIFFE identity is required for mastering (ADR-0008).

### Path A — Linux / cloud K3s

```bash
# on server nodes
bash deploy/k3s/install-server.sh
# on agents
bash deploy/k3s/install-agent.sh
make cilium-install   # when ready for eBPF networking
make cluster-install PROFILE=k8s-secure
make k3s-check        # kube-bench style checks when available
```

### Path B — macOS via Lima

```bash
make lima-k3s-up
make cluster-install PROFILE=k8s-secure
```

Guides: [Secure cluster](deployment/k8s-secure.md), [macOS](deployment/macos.md).

**Checkpoint:** Governor mode is `enforce`; unauthenticated privileged calls
fail; kill switch works (`make governor-kill` / runbook).

---

## 8. P4 Platform + evidence

```bash
make cluster-install PROFILE=platform
make kubeflow-install          # when cluster ready
make kubeflow-register-models  # stub registry entries
make lineage-report DOC=<sha256>
make annex-iv
make audit-evidence
make audit-compliance          # OPA EU article audit → reports/compliance/eu-audit/
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

---

## Where to go next

| If you want… | Open |
|--------------|------|
| Architecture diagrams & data model | [Architecture](architecture/index.md) |
| Pipeline stages | [Tools overview](tools/tools_overview.md) |
| Vespa schema / RAG | [Vespa RAG](tools/vespa_rag.md) |
| MCP / agents / templates | [MCP](tools/mcp.md), [Agents](tools/agents.md), [Templates](tools/templates.md) |
| Ingest API | [Ingestion](deployment/ingest.md) |
| Audit / WORM | [Audit store](deployment/audit.md) |
| Governor | [Governor](deployment/governor.md) |
| Security model | [Security](security.md) |
| EU compliance OPA | [EU Compliance OPA Audit](compliance/eu-audit.md) |
| Design decisions | [ADRs](adr/index.md) |

```bash
make help   # every Make target with a one-line description
```
