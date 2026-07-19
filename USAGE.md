# T-KEIR usage (legacy entry point)

> **Prefer:** [Zero to Hero](tkeir/docs/zero_to_hero.md) (dev → prod), or from
> `tkeir/` run `uv run mkdocs serve` and open that page in the nav.
>
> Also: [Dev Container](devcontainer.md), [Quickstart](ready_to_run.md),
> [Vespa RAG](tools/vespa_rag.md).

This file summarizes the current OSS workflow. REST `_svc.py` / `_client.py` services
were removed; analysis runs through the unified in-process pipeline.

## Requirements

- Python **>= 3.10** (development uses **3.11**)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Tesseract OCR (optional, for scanned PDFs)
- Docker (optional, for Vespa RAG)

## Directory layout

| Path | Role |
|---|---|
| `tkeir/thot/` | Core NLP tasks |
| `tkeir/thot/tools/` | CLI tools (pipeline, Vespa, annotation) |
| `tkeir/configs/` | Pipeline and tagger configuration |
| `tkeir/resources/modeling/tokenizer/` | Lexicons and `tkeir_mwe.pkl` |
| `tkeir/tests/indexing/` | Portable PDF + pipeline JSON fixtures for Vespa |
| `vespa/` | Vespa Docker schemas/scripts (use root `Makefile` targets) |
| `tkeir-hmi/` | Next.js Search & RAG web interface |

## Setup

```bash
make setup          # from repository root
make init-models    # build annotation pickle only
```

## Run the pipeline

Use **`-t auto`** (default) so PDFs and Office files are converted with MarkItDown.
Use **`-t raw`** only for plain-text inputs (`.txt`, `.md`, …).

```bash
tkeir-pipeline \
  -c tkeir/configs/pipeline.yaml \
  -i <INPUT FILE OR DIR> \
  -o <OUTPUT DIR> \
  -t auto
```

Or from the repository root:

```bash
make pipeline PIPELINE_INPUT=tkeir/tests/fixtures/test-raw/raw PIPELINE_OUTPUT=/tmp/out
make quickstart
```

`make pipeline` runs `install-spacy-models` automatically. MWE compound-word
detection is **disabled** by default (`use-mwe: false` in configs); pass
`--use-mwe` to `tkeir-pipeline` only when needed.

## Vespa indexing and RAG

Vespa uses **streaming mode**. Without Keycloak, index and query use the
shared group **`dev@tkeir`** (`VESPA_USER_SPACE`). Signed-in users get an
isolated group from the JWT — see [Vespa RAG](tkeir/docs/tools/vespa_rag.md)
and [Zero to Hero](tkeir/docs/zero_to_hero.md).

```bash
# From repository root
export VESPA_USER_SPACE=dev@tkeir   # optional; this is already the default
make bootstrap
make index-fixtures   # optional: (re)build tkeir/tests/indexing/output from PDFs
make index
make rag
make rag-query RAG_QUERY="your question"
```

`make index` requires `*.pipeline.json` files under `tkeir/tests/indexing/output`.
Run `make index-fixtures` first if that directory is empty.
After switching from indexed → streaming, wipe Vespa (`bash vespa/clean_db.sh`)
then re-bootstrap and re-index.

## Human-Machine Interface (tkeir-hmi)

```bash
make rag                                    # terminal 1 — FastAPI on :8090
cd tkeir-hmi && npm install && npm run dev   # terminal 2 — UI on :3000
```

See [tkeir/docs/hmi.md](tkeir/docs/hmi.md).

## Dev container

See [tkeir/docs/devcontainer.md](tkeir/docs/devcontainer.md).

Open the repository root in Cursor or VS Code → Command Palette (`Cmd+Shift+P`) →
**Dev Containers: Reopen in Container**. Or from the host terminal: `make devcontainer`
(see [tkeir/docs/devcontainer.md](tkeir/docs/devcontainer.md)).

## API documentation

Documented Python examples are tested in `tkeir/tests/unittests/TestToolsDocExamples.py`.
See [tools/api_reference.md](tkeir/docs/tools/api_reference.md).
