# T-KEIR usage

Short cheat sheet for day-to-day commands. For the full journey (P0 → P4), use
**[Zero to Hero](docs/zero_to_hero.md)**. Browse the docs site after setup:

```bash
make setup
make docs          # http://127.0.0.1:8000/
```

Also useful: [Installation](docs/installation.md), [NLP quickstart](docs/ready_to_run.md),
[Environment variables](docs/deployment/environment.md), [Vespa RAG](docs/tools/vespa_rag.md),
[Dev Container](docs/devcontainer.md).

Analysis runs through the unified in-process pipeline (`tkeir-pipeline`). Legacy
REST `_svc.py` / `_client.py` services were removed.

## Requirements

- Python **≥ 3.10** (Makefile default **3.11**)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Docker (Vespa, Compose, dev container)
- Tesseract OCR (optional, scanned PDFs)
- Ollama on the host when `PROVIDER=ollama` (default)

## Directory layout

| Path | Role |
|------|------|
| `docs/` | MkDocs site (`make docs`) |
| `tkeir/thot/` | Core NLP, RAG, ingest, audit, governor, agents, MCP |
| `tkeir/thot/tools/` | CLIs: pipeline, Vespa indexer, RAG API, BEIR eval |
| `tkeir/configs/` | Pipeline, taggers, RAG, agents, workflows, templates |
| `tkeir/resources/` | Lexicons, MWE trie, modeling assets |
| `vespa/` | Vespa schemas / Docker helpers |
| `tkeir-hmi/` | Next.js Search / RAG / admin UI |
| `deploy/` | Compose, Helm, Keycloak, SPIRE, images |
| `datasets/` | BEIR downloads (`make beir-eval`) |
| `results/beir/` | Intermediate BEIR reports (gitignored) |

## Setup

```bash
make setup          # uv sync, spaCy models, Tesseract check
make init-models    # annotation pickle only (optional MWE)
```

Dev container: `make devcontainer` or **Dev Containers: Reopen in Container**.
Details: [docs/devcontainer.md](docs/devcontainer.md).

## Pipeline (NLP)

Use **`-t auto`** for PDF/Office; **`-t raw`** for plain text only.

```bash
make quickstart     # fixtures → output/quickstart/

tkeir-pipeline \
  -c tkeir/configs/pipeline.yaml \
  -i <INPUT FILE OR DIR> \
  -o <OUTPUT DIR> \
  -t auto

make pipeline \
  PIPELINE_INPUT=tkeir/tests/fixtures/test-raw/raw \
  PIPELINE_OUTPUT=/tmp/out
```

`make pipeline` installs spaCy models automatically. MWE compounds are off by
default; pass `--use-mwe` only when needed.

## Vespa indexing and RAG

Streaming mode. Without Keycloak, group is **`dev@tkeir`** (`VESPA_USER_SPACE`).
Signed-in users get a JWT-scoped group — see [Vespa RAG](docs/tools/vespa_rag.md).

```bash
export VESPA_USER_SPACE=dev@tkeir   # optional; already the default
make bootstrap
make index-fixtures                # build fixture *.pipeline.json if needed
make index
make rag                           # FastAPI :8090
make rag-query RAG_QUERY="your question"
```

After switching indexed → streaming, wipe Vespa (`bash vespa/clean_db.sh`), then
re-bootstrap and re-index.

## HMI

```bash
make rag                                    # terminal 1 — API :8090
cd tkeir-hmi && npm install && npm run dev   # terminal 2 — UI :3000
```

See [docs/hmi.md](docs/hmi.md). Auth / proxy env vars:
[Environment variables](docs/deployment/environment.md#hmi-nextjs).

## Agents, MCP, Compose (optional)

```bash
make agent                  # agent API :8092 (needs RAG / LLM)
make mcp                    # MCP HTTP :8093 (or MCP_STDIO=1)
make compose-up PROFILES=core,auth
make compose-bootstrap      # Vespa schemas inside Compose
```

Docs: [Agents](docs/tools/agents.md), [MCP](docs/tools/mcp.md),
[Compose](docs/deployment/compose.md), [SPIFFE](docs/deployment/spire.md).

## Evaluation (BEIR)

```bash
make beir-eval                              # scifact fiqa arguana
make beir-eval BEIR_DATASETS=scifact
```

Writes `docs/evaluation_report.md` and intermediate
`results/beir/<dataset>/report.md` after each dataset.
See [Evaluation](docs/evaluation.md).

## Quality / docs

```bash
make help
make pre-commit             # fast local gates
make ci                     # full quality gate
make docs                   # MkDocs :8000
make docs-build             # static site/ 
```

## API examples

Documented Python snippets are tested in
`tkeir/tests/unittests/TestToolsDocExamples.py`.
See [API reference](docs/tools/api_reference.md).
