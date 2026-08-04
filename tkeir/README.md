# T-KEIR

**T-KEIR** (Thales Knowledge Extraction to Information Retrieval) is a document
analysis toolkit: unified NLP pipeline, Vespa hybrid search / RAG, HMI, MCP,
and governed agents. Sources live under `thot/`; buildable docs under `docs/`.

## Documentation

Full site sources are in **`docs/`** (MkDocs Material). After installing
dependencies from the **repository root**:

```shell
make setup          # uv sync + project deps (once)
make docs           # http://127.0.0.1:8000/  (override: DOCS_PORT=8001)
```

Or from the repository root with uv:

```shell
uv run --project tkeir --with mkdocs --with mkdocs-material \
  --with mkdocs-render-swagger-plugin \
  mkdocs serve -f mkdocs.yml -a 127.0.0.1:8000
```

Static build / PDF (optional): `make docs-build`, `make docs-pdf`.

### Site map (nav tabs)

| Tab | What it covers |
|-----|----------------|
| **Home** | Product intro, feature list, changelog pointers |
| **Zero to Hero** | End-to-end path P0→P4; **NLP** page = pipeline quickstart without Vespa |
| **Overview** | Pipeline stages, agentic layer, RAG path at a glance |
| **Architecture** | Service topology, data/sequence flows, schemas, ADR index |
| **Conception** | Design notes: services, modules, storage, config surfaces |
| **Installation** | Host prereqs, `make setup`, models, TLS/proxy tips |
| **Dev Container** | VS Code / Codespaces layout and first commands |
| **Deployment** | Profiles, **environment variables**, Compose, k8s, audit, governor, SPIRE |
| **Evaluation** | BEIR datasets (SciFact, FiQA, ArguAna), how to run, scored report |
| **Tools** | CLIs and APIs: pipeline taggers, Vespa RAG, MCP, agents, templates, HMI, corpus |
| **Regularity component** | Identity of Action (ActionRecords) and Mastering of Action (governor) |
| **Compliance** | EU AI Act, CRA, NIS2, DORA, GDPR, PLD; OPA audit and evidence pipeline |
| **Quality** | Code-quality dashboard (complexity, licenses) |
| **Runbooks** | Kill switch, agent runaway, injection, rollback, DSR/forget, incidents |
| **ADR** | Architecture decision records (platform, ingest, audit, agents, SPIFFE, …) |
| **Security** | Threat model and hardening notes |
| **Operation and Management** | Day-2 ops (health, metrics, admin) |
| **About** | Copyright and contact |

Published HTML (when available): [ThalesGroup.github.io/t-keir](https://thalesgroup.github.io/t-keir). Prefer **`make docs`** for the tree that matches this checkout.

## Directory structure

| Path | Role |
|------|------|
| `scripts` | Helpers (e.g. `init-models.sh` for MWE trie) |
| `configs` | Bundled service and pipeline YAML |
| `../docs` | MkDocs documentation (repository root) |
| `resources` | Lexical resources and tagger rules |
| `thot` | Python package (core NLP + tools) |
| `thot/tools/ingest` | Passage indexing into Vespa |
| `thot/tools/search` | Retrieval / RAG API |
| `thot/tools/eval` | BEIR smoke + full evaluation |
| `resources/modeling/net` | Local neural weights (BGE-M3 via `make pull-bge-model`) |

## Installation

**Python 3.10–3.12** (`requires-python = ">=3.10,<3.13"`). **3.11** is the
default for Make, CI, and images; override with `make setup PYTHON=3.12`.
**3.13+** is not supported yet. See
[Installation — Python versions](../docs/installation.md#python-versions).

Also requires [uv](https://docs.astral.sh/uv/getting-started/installation/).
Git is required to clone the repository.

From the **repository root** (recommended):

```shell
make setup
```

Other options:

1. **uv / wheel** — `uv build` then `pip install dist/*.whl` in a venv
2. **Dev container** — reopen `.devcontainer/`, then `make setup`
3. **Compose** — `make images` + `make compose-up` (see deployment docs)

If **pycurl** fails to build on Debian/Ubuntu:

```shell
sudo apt install libcurl4-openssl-dev libssl-dev
```

### Configure and models

Edit configs under **`configs/`**. Load the tokenizer MWE model with:

```shell
# From repository root (preferred)
make init-models

# Or from tkeir/
./scripts/init-models.sh [MODEL_CACHE_PATH]
```

Set `TRANSFORMERS_CACHE` to that model path before running model-backed tools.
`make pipeline` / `make setup` also pull spaCy models as needed.

### Resources

Tokenizer resources live under
`resources/modeling/tokenizer/[en|fr|…]`. See
`resources/modeling/tokenizer/en/annotation-resources.json` for file roles.

## Quick start

```shell
# From repository root
make setup
make quickstart          # NLP pipeline on fixtures → output/quickstart/
```

Analyse your own documents (`-t auto` for PDF/Office; `-t raw` for plain text):

```shell
tkeir-pipeline -c tkeir/configs/pipeline.yaml -i <INPUT> -o <OUTPUT DIR> -t auto
```

Pipeline order: converter → language → resources → tokenizer → morphosyntax →
NER → syntax → keywords. MWE compounds are off by default; use `make init-models`
and `--use-mwe` when needed.

### Vespa indexing and RAG

```shell
make bootstrap           # Vespa + schemas
make index-fixtures      # optional fixture index set
make index               # index *.pipeline.json
make rag                 # FastAPI RAG on :8090
```

### Tool layout (`thot/tools/`)

| Module | Purpose |
|--------|---------|
| `pipeline.py` | Document analysis (`tkeir-pipeline`) |
| `search/` | Vespa indexing, RAG API, BEIR eval |
| `annotation/` | MWE trie compilation |

For the full journey (RAG, HMI, agents, Compose, secure k8s), open the docs
(`make docs`) and follow **Zero to Hero**.
