# T-KEIR

**T-KEIR 2.0.0** is a document analysis and retrieval toolkit by Thales.
It runs a unified NLP pipeline on documents, indexes them in [Vespa](https://vespa.ai/),
exposes hybrid search plus RAG through a FastAPI backend and a Next.js HMI,
and includes an **agentic layer** (MCP tools, multi-agent workflows, ontology-driven
templates) under the platform governor.

Full documentation: [ThalesGroup.github.io/t-keir](https://thalesgroup.github.io/t-keir)

## What it does

- **Document conversion** — plain text, PDF, Office, HTML, email (MarkItDown + optional OCR)
- **NLP pipeline** — language detection, tokenizer, morphosyntax, NER, syntax, keywords
- **Ontology export** — entity/keyword graphs for RAG and the HMI
- **Vespa RAG** — passage schemas (`global` + `user`), BGE-M3 hybrid retrieval, LLM answers
- **MCP server** — scoped corpus tools for external MCP clients (`tkeir-mcp`)
- **Agents & workflows** — configurable researchers/analysts/writers, multi-agent
  plans, grounded template composition, approval-gated publish (`tkeir-agent`)
- **Web UI** — search, ontology explorer, agent run monitor (`tkeir-hmi/`)

## Repository layout

| Path | Role |
|---|---|
| `tkeir/thot/` | Core pipeline tasks and runtime |
| `tkeir/thot/tools/` | CLI: `tkeir-pipeline`, Vespa indexer, RAG API |
| `tkeir/thot/mcp/` | MCP server + outbound client |
| `tkeir/thot/agent/` | Agent loop, orchestrator, publish |
| `tkeir/thot/compose/` | Ontology-driven template composition |
| `tkeir/configs/` | Pipeline, taggers, RAG, agents, workflows, templates |
| `vespa/` | Vespa Docker schemas and shell scripts (targets in root `Makefile`) |
| `tkeir-hmi/` | Next.js Human-Machine Interface |
| `deploy/` | Compose, Helm charts, Keycloak realm, K3s — see [INSTALL.md](INSTALL.md) |
| `.devcontainer/` | Reproducible dev environment (Python 3.11, uv, Tesseract, Docker socket) |

Installation profiles (P0 local → P4 platform): start with
**[Zero to Hero](docs/zero_to_hero.md)**, then [INSTALL.md](INSTALL.md) and
[deployment docs](docs/deployment/index.md).

## Quick start

### 1. Dev container (recommended)

Requires [Docker Desktop](https://docs.docker.com/get-docker/) running on the host.

**Terminal (no IDE):**

```bash
make devcontainer
# or: bash .devcontainer/enter-devcontainer.sh
```

**Cursor / VS Code:** open the repo root → Command Palette → **Dev Containers: Reopen in Container**.

Inside the container (`/workspace`):

```bash
make setup          # Python deps, spaCy, Tesseract, MWE pickle, BGE-M3
```

If `uv sync` fails because of a host-built `tkeir/.venv`, run
`bash .devcontainer/ensure-venv.sh && make install` inside the container, or
`rm -rf tkeir/.venv` on the host and retry.

Details: [docs/devcontainer.md](docs/devcontainer.md)

### 2. Pipeline demo (local, no Vespa)

```bash
make setup
make quickstart
```

Runs `tkeir-pipeline` on bundled fixtures under `tests/fixtures/` and writes
results to `output/quickstart/`.

### 3. Vespa stack — bootstrap, index, RAG

Ollama must be running on the **host** when using the default `PROVIDER=ollama`
(`ollama serve`, models `bge-m3` and `mistral-nemo`).

```bash
# From repository root
make install           # uv sync in tkeir/
make bootstrap         # start Vespa + deploy schemas

# Build pipeline JSON from example PDFs (if output/ is empty)
make index-fixtures    # tests/indexing/input → output/

# Index passages into Vespa (BGE-M3 dense+sparse from resources/modeling/net)
export PROVIDER=ollama
export EMBEDDING_MODEL=bge-m3
export LLM_MODEL=mistral-nemo
make index

# Start FastAPI RAG API on :8090
make rag

# Sample query
make rag-query RAG_QUERY="Who is Rob Brown?"
```

Indexing reads `tests/indexing/output/*.pipeline.json` by default.
Override with `INDEX_INPUT=/path/to/json/dir make index`.

Details: [vespa/README.md](vespa/README.md), [docs/tools/vespa_rag.md](docs/tools/vespa_rag.md)

### 4. Hybrid demo — `./start_services.sh` (recommended)

One-command launcher for the full local stack in **tmux**: Vespa + Keycloak +
SPIRE (Docker), then ingest, RAG, governor, audit, OKF, agent, and HMI on the
host, with health gates between windows.

```bash
# Prerequisites: make setup (+ make pull-vespa), Docker, tmux, Ollama on host
./start_services.sh
# or: bash start_services.sh --no-attach
```

| Shortcut | Action |
|---|---|
| `TAB` | Next tmux window |
| `CTRL+R` | Restart the active pane |
| `ESC` | `make down` + kill session (`KEEP_DATA=1` keeps DBs) |

Open [http://localhost:3000](http://localhost:3000) when the `[HMI]` window is
ready. Skip the install gate with `--skip-check-install` if the toolchain is
already verified.

Details: [docs/deployment/start_services.md](docs/deployment/start_services.md),
[Zero to Hero §5.2.a](docs/zero_to_hero.md#52a-hybrid-demo-vespa--keycloak--spire-infra-host-services)

### 5. Web UI (HMI) only

With Vespa indexed and `make rag` running (or after `./start_services.sh`):

```bash
cd tkeir-hmi
npm install
cp .env.local.example .env.local   # optional
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The UI proxies `/api/*` to the
RAG API on port 8090.

Details: [docs/hmi.md](docs/hmi.md)

## Document converter

The **converter** is the first pipeline step. It turns files into T-KEIR JSON
(`title`, `content`, metadata) for downstream tagging and indexing.

### Supported input types

Conversion uses [Microsoft MarkItDown](https://github.com/microsoft/markitdown).
Typical formats:

| Type | Examples |
|---|---|
| Plain text | `.txt`, `.md`, `.csv` (as text) |
| PDF | `.pdf` |
| Office | `.docx`, `.pptx`, `.xlsx` |
| Web / markup | `.html`, `.htm` |
| Email | `.eml`, mail folders |
| Existing JSON | T-KEIR documents (`tkeir` datatype — pass-through) |

Use **`-t auto`** (default) so the pipeline detects format from extension and magic
bytes. Use **`-t raw`** only for plain UTF-8 text — never on PDFs or binary files
(that would decode bytes as garbage text).

```bash
tkeir-pipeline -c tkeir/configs/pipeline.yaml \
  -i path/to/docs -o output/ -t auto
```

Or via Makefile:

```bash
make pipeline PIPELINE_INPUT=path/to/docs PIPELINE_OUTPUT=output/
```

### PDF text layer and OCR

MarkItDown extracts the PDF **text layer** by default. Text trapped in images
(scans, diagrams, screenshots) is recovered when OCR is enabled in
`tkeir/configs/converter.yaml`:

```json
"ocr": {
  "enabled": true,
  "mode": "tesseract",
  "min-image-pixels": 10000,
  "min-page-text-chars": 40,
  "render-dpi": 200
}
```

| Mode | Requirement |
|---|---|
| `tesseract` | [Tesseract](https://github.com/tesseract-ocr/tesseract) on `PATH` (`eng` + `fra` in devcontainer) |
| `llm` | `"mode": "llm"` + `OPENAI_API_KEY` (or `ocr.llm-api-key`) for vision-based extraction |

The devcontainer and `make setup` install Tesseract for PDF OCR in the pipeline.

Details: [docs/tools/converter.md](docs/tools/converter.md)

## Makefile reference

Run `make help` at the repository root for a short list. One root `Makefile` drives
setup, pipeline, tests, docs, Vespa, indexing, and RAG.

### Setup & pipeline

| Target | Description |
|---|---|
| `make help` | List common targets and variables |
| `make setup` | Full local setup: `install` + spaCy + Tesseract + `init-models` + BGE-M3 download |
| `make install` | `uv sync` in `tkeir/` (dev dependency group) |
| `make install-spacy-models` | Download spaCy language models used by the pipeline |
| `make install-tesseract` | Install Tesseract OCR (PDF image text) |
| `make init-models` | Build `tkeir_mwe.pkl` from annotation resources (optional MWE) |
| `make pipeline` | Run `tkeir-pipeline` on `PIPELINE_INPUT` → `PIPELINE_OUTPUT` |
| `make quickstart` | Pipeline demo on bundled fixtures → `output/quickstart/` |
| `make devcontainer` | Start devcontainer and open a shell (`/workspace`) |
| `make build` | Build Python wheel → `dist/` |
| `make build` | Build wheel → `dist/*.whl` |
| `make clean` | Remove build artifacts, caches, coverage reports |

**Pipeline variables** (override on the command line):

| Variable | Default | Purpose |
|---|---|---|
| `PIPELINE_INPUT` | `tests/fixtures/test-raw/raw` | Input file or directory |
| `PIPELINE_OUTPUT` | `/tmp/tkeir-pipeline-out` | Output directory for JSON |
| `PIPELINE_TYPE` | `auto` | Input type: `auto`, `raw`, `pdf`, … |
| `PIPELINE_CONFIG` | `tkeir/configs/pipeline.yaml` | Pipeline configuration |
| `TRANSFORMERS_CACHE` | `.cache/models` | Hugging Face hub cache (rerankers, etc.; **not** BGE-M3) |

Example:

```bash
make pipeline \
  PIPELINE_INPUT=docs/ \
  PIPELINE_OUTPUT=output/my-run/ \
  PIPELINE_TYPE=auto
```

### Quality & docs

| Target | Description |
|---|---|
| `make test` | Unit + functional test suites |
| `make test-unit` | Unit tests only (`tests/unittests/`) |
| `make test-functional` | Functional tests only |
| `make coverage` | Coverage run (90% fail-under) |
| `make lint` | `black` + `isort` checks |
| `make format` | Apply `black` + `isort` |
| `make typecheck` | `mypy` on `thot/` and `tests/` |
| `make liccheck` | Verify dependency licenses |
| `make complexity` | `radon` + `xenon` complexity gates |
| `make pip-audit` | Scan dependencies for known CVEs |
| `make bom` | CycloneDX SBOM + AIBOM → `reports/bom/` |
| `make trivy` | Filesystem/config security scan (Docker) |
| `make owasp-dependency-check` | OWASP Dependency-Check (Docker) |
| `make security-report` | Unified security index → `reports/security/` |
| `make slsa-report` | SLSA provenance + upgrade roadmap → `reports/slsa/` |
| `make ci` | Full local gate (lint, types, tests, coverage, security, BOM, SLSA, compliance, docs) |
| `make docs` | MkDocs dev server → http://127.0.0.1:8000 |
| `make docs-build` | Static site → `site/` |

CI reports, GitHub Actions, and gate thresholds are documented under
[`docs/ci/`](docs/ci/index.md) (MkDocs nav: **CI & reports**).

### Search & RAG (Vespa)

| Target | Description |
|---|---|
| `make pull-bge-model` | Download `BAAI/bge-m3` into `tkeir/resources/modeling/net/bge-m3` (skip if ready; `FORCE_BGE=1` to refresh) |
| `make pull-models` | Download BGE-M3 + pull Ollama embedding/LLM models |
| `make eval` / `make eval-smoke` | Aliases for `beir-eval` / `beir-smoke` |
| `make start` | Start Vespa Docker container |
| `make init` | Deploy schemas (Vespa must already be running) |
| `make bootstrap` | `start` + deploy schemas |
| `make vespa-check` | Vespa health check |
| `make test-vespa` | Vespa query smoke test |
| `make test-vespa-py` | Python unit tests for search tools |
| `make index-fixtures` | Pipeline on `tests/indexing/input/` → `output/` |
| `make index` | Embed and index `*.pipeline.json` into Vespa |
| `make rag` | Start FastAPI RAG API on port **8090** |
| `make rag-query` | `curl` sample RAG request |
| `make mcp` | Start MCP server on port **8093** |
| `make agent` | Start agent / workflow service on port **8092** |
| `make agent-run` | Create a single-agent run and poll (`GOAL=…`) |
| `make workflow-run` | Create a workflow run and poll (`WORKFLOW=content_brief`) |
| `make compose` | Ontology template compose (`TEMPLATE=synthesis_note`) |
| `make beir-eval` | BEIR IR eval → `docs/evaluation_report.md` + `reports/beir/` (`BEIR_DATASETS=scifact` for one) |
| `make clean-db` | Wipe Vespa data volume (then re-run `bootstrap`) |
| `make vespa-clean` | Stop/remove Vespa container (keeps volume) |
| `make logs` | Tail Vespa Docker logs |

**Vespa / BEIR variables:**

| Variable | Default | Purpose |
|---|---|---|
| `INDEX_INPUT` | `tests/indexing/output` | Directory of `*.pipeline.json` to index |
| `PROVIDER` | `ollama` | LLM/embeddings provider (`openai`, `ollama`, `vllm`) |
| `EMBEDDING_MODEL` | provider-specific | Embedding model (e.g. `bge-m3`) |
| `LLM_MODEL` | provider-specific | Generation model (e.g. `mistral-nemo`) |
| `RAG_QUERY` | `Who is Rob Brown?` | Query for `make rag-query` |
| `RAG_URL` | `http://localhost:8090` | RAG API base URL |
| `BEIR_DATASETS` | `scifact fiqa arguana scidocs` | Space-separated datasets; one: `BEIR_DATASETS=scifact` |
| `BEIR_EXTRA` | _(empty)_ | Extra flags, e.g. `--skip-dense` |
| `BEIR_REPORT` | _(empty)_ | Optional extra report copy (docs report always written) |

All targets run from the **repository root** (`make help` for the short list).

### Typical command chains

```bash
# Local pipeline only
make setup && make quickstart

# Full RAG stack (from repo root)
make setup
make bootstrap && make index-fixtures && make index && make rag

# CI before pushing
make ci
```

## License

See MIT license files.
