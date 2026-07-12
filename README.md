# Theresis NLP Tools

Set of tool for NLP purposes, developped by Theresis.
The T-KEIR tools allows to apply numerous NLP tools, search, index and classify. The tools cover


  * advanced tokenizer configuration
  * named entities with validations rules
  * keywords extraction
  * SVO based on syntactic dependencies and rules
  * automatic summarization
  * sentiment analysis
  * unsupervised classification
  * relation clustering
  * question and answering
  * advanced query formulation and expansion based on clustering and text analysis

Documentation is available directly on [Thalesgroup.github.io](https://thalesgroup.github.io/t-keir)

## Repository layout

| Path | Role |
|---|---|
| `tkeir/thot/` | Core NLP pipeline tasks and runtime |
| `tkeir/thot/tools/` | CLI tools: pipeline, Vespa search/RAG, annotation resources |
| `tkeir/configs/` | Bundled configuration (pipeline, taggers, `rag-prompts.yaml`) |
| `vespa/` | Vespa Docker deployment (schemas, shell scripts); Makefile calls `thot.tools.search` |
| `tkeir-hmi/` | Next.js Human-Machine Interface for Search & RAG |

Quick start: `make setup` then `make quickstart`. Vespa RAG: `cd vespa && make bootstrap && make index && make rag`. Web UI: `cd tkeir-hmi && npm install && npm run dev` (see [tkeir/docs/hmi.md](tkeir/docs/hmi.md)).

**Dev container (recommended for development):** `make devcontainer` or
`bash .devcontainer/enter-devcontainer.sh` from the host; or open the repo in Cursor/VS Code →
**Dev Containers: Reopen in Container**. See [tkeir/docs/devcontainer.md](tkeir/docs/devcontainer.md).
