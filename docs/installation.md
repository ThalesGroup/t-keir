# Installation

> New users: follow **[Zero to Hero](zero_to_hero.md)** end-to-end (P0 → P4).
> This page is the detailed **P0** install reference.

This page covers installing T-KEIR for **local development (profile P0)**. All Make
targets run from the **repository root**. Run `make help` for the full target list.

For Compose, Kubernetes, and secured cluster profiles, see
[Deployment profiles](deployment/index.md) and the root `INSTALL.md`.

## Requirements

| Tool | Notes |
|---|---|
| **Git** | Clone and version identity (`make build`, `make tag`) |
| **[uv](https://docs.astral.sh/uv/getting-started/installation/)** | Python package manager (installs Python **3.11** if needed) |
| **Make** | GNU Make or BSD Make (macOS Command Line Tools) |
| **Docker** (optional) | Required for the [dev container](devcontainer.md), Vespa, and security scans |
| **curl** / **jq** (optional) | Required for `make rag-query` and `make smoke-test` |

Supported host platforms: Linux (Ubuntu / AlmaLinux / similar), macOS, WSL2.

Python **≥ 3.10** is required; the Makefile defaults to **3.11** (`PYTHON=3.11`).

## 1. Clone the repository

```bash
git clone https://github.com/ThalesGroup/t-keir.git
cd t-keir
```

## 2. Choose an install path

### Option A — Host install (recommended for day-to-day work)

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if needed:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

From the repository root:

```bash
make setup
```

This runs, in order:

1. `uv sync` (dev dependencies into `tkeir/.venv`)
2. spaCy language models (skips if already importable; `FORCE_SPACY_MODELS=1` to force)
3. Tesseract OCR check / install helper
4. tokenizer MWE resource (`tkeir_mwe.pkl`; skips if present)
5. BGE-M3 into `tkeir/resources/modeling/net/bge-m3` (skips if ready; `FORCE_BGE=1` to refresh)

Verify:

```bash
make verify-lockfile
cd tkeir && uv run --python 3.11 python -c "import thot; print('OK', thot.__file__)"
```

### Option B — Dev container (recommended for a clean, reproducible env)

Requires Docker Desktop (or Engine + Compose v2) running on the host.

```bash
make devcontainer
# inside /workspace:
make setup
```

Or in Cursor / VS Code: **Dev Containers: Reopen in Container**, then `make setup`.

Full details: [Dev Container](devcontainer.md).

### Option C — Wheel install (packaging)

Build an installable wheel (rebuilds only when sources change):

```bash
make build
# → dist/*.whl  (stamp: dist/.build_timestamp)
```

Install into a venv:

```bash
uv build --directory tkeir
python3 -m venv $HOME/tkeirenv
source $HOME/tkeirenv/bin/activate
pip install dist/tkeir-*.whl
```

Prefer **Option A** (`make setup`) for development. Models: `make init-models`
(or `tkeir/scripts/init-models.sh`).

## 3. Configuration and resources

| Path | Purpose |
|---|---|
| `tkeir/configs/` | Pipeline and task YAML (`pipeline.yaml`, taggers, `rag.yaml`, …) |
| `tkeir/resources/modeling/tokenizer/<lang>/` | Lexicons, rules, `annotation-resources.json` |
| `tkeir/resources/modeling/tokenizer/en/tkeir_mwe.pkl` | Compiled MWE trie (`make init-models`) |
| `tkeir/resources/modeling/net/bge-m3/` | Local BGE-M3 weights (`make pull-bge-model` / `make setup`) |

Resource paths inside configs are resolved relative to the `tkeir/` package root.
BGE-M3 is **not** loaded from the Hugging Face hub cache; FlagEmbedding reads
only `resources/modeling/net/bge-m3`. Other HF artifacts (e.g. cross-encoders)
may still use:

```bash
export TRANSFORMERS_CACHE=$PWD/.cache/models
```
## 4. What to run next

| Goal | Command |
|---|---|
| Pipeline demo on fixtures | `make quickstart` → [NLP](ready_to_run.md) |
| Analyse your own files | `make pipeline PIPELINE_INPUT=… PIPELINE_OUTPUT=…` |
| Vespa + RAG | `make bootstrap && make index-fixtures && make index && make rag` → [Vespa RAG](tools/vespa_rag.md) |
| Quality gate before push | `make pre-commit` or `make ci` |
| Docs site | `make docs` |
| Docs PDF | `make docs-pdf` → `output/docs/tkeir-docs.pdf` |
| Environment variables | [Environment variables](deployment/environment.md) |
| EU compliance OPA audit | `make audit-compliance` → [EU Compliance OPA Audit](compliance/eu-audit.md) |

## Troubleshooting

**Enterprise TLS / proxy** — `uv sync` or BEIR downloads fail with certificate errors.
See [Dev Container — Troubleshooting](devcontainer.md#troubleshooting) and
`source export_certif_macos.source` on macOS (`SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`).

**`uv sync` fails on `.venv` inside the dev container** — host and container virtualenvs collide:

```bash
bash .devcontainer/ensure-venv.sh
make install
```

**Missing spaCy models** — pipeline or RAG query refinement fails:

```bash
make install-spacy-models
```

**Tesseract / PDF OCR** — scanned PDFs need OCR:

```bash
make install-tesseract
```

**`.env` secrets** — never commit `.env`. CI runs `make check-secrets` to block
tracked credential files and high-confidence secret patterns.

**Lock file drift** — after editing `tkeir/pyproject.toml`:

```bash
cd tkeir && uv lock
# or: make deps-update
make verify-lockfile
```
