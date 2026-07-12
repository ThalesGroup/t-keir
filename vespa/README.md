# Vespa 2-Level RAG Stack

This directory contains the Vespa Docker deployment (schemas, shell scripts).
Python indexing and RAG services live in `tkeir/thot/tools/search/`.

- **`tkeir_document` schema** — parent documents with BM25 on `title` and `content`
- **`chunk` schema** — child chunks with HNSW on `chunk_embedding` and
  `questions_embeddings`, hybrid ranking against parent BM25 fields
- **Ontology** — stored as raw Turtle in `rdf_graph_serialized` and merged
  locally at RAG time (not indexed as a graph in Vespa)

## Quick start

```bash
cd vespa

# 1. Install Python dependencies (via tkeir package)
make sync

# 2. Start Vespa and deploy schemas
make bootstrap

# 3. Build pipeline JSON fixtures (if needed) and index
export PROVIDER=ollama
export EMBEDDING_MODEL=bge-m3
export LLM_MODEL=mistral-nemo
make index-fixtures   # PDFs in tkeir/tests/indexing/input → output/
make index

# 4. Run the FastAPI RAG API
make rag

# 5. Sample query
make rag-query RAG_QUERY="Who is Rob Brown?"
```

Default indexing input: `tkeir/tests/indexing/output` (override with `INDEX_INPUT`).

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PROVIDER` | `ollama` | `openai`, `ollama`, or `vllm` |
| `EMBEDDING_MODEL` | provider-specific | Embedding model name |
| `LLM_MODEL` | provider-specific | Generation model name |
| `EMBEDDING_DIM` | `384` | Embedding dimension (must match schemas) |
| `VESPA_URL` | `http://localhost:8080` | Vespa endpoint |
| `OPENAI_API_KEY` | — | API key for OpenAI / vLLM |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `VLLM_BASE_URL` | `http://localhost:8000/v1` | vLLM OpenAI-compatible endpoint |
| `RAG_HOST` / `RAG_PORT` | `0.0.0.0` / `8090` | FastAPI bind address |
| `RAG_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Allowed browser origins for the RAG API |

RAG prompts: `tkeir/configs/rag-prompts.yaml` (`unavailable_answer`, `no_chunks_message` per language).

## API

- `GET /health` — Vespa availability
- `POST /rag/query` — hybrid retrieval + ontology merge + generation

Response includes `ontology` with high-value `entities` (NER) and `keywords`, each
linked to retrieved `chunk_ids`.

## Makefile targets

```bash
make sync       # uv sync in tkeir/
make start      # docker run Vespa
make init       # deploy schemas (Vespa already running)
make bootstrap  # start + deploy schemas
make check      # health check
make test       # Vespa query smoke test
make test-py    # Python unit tests (tkeir)
make index-fixtures  # pipeline on tkeir/tests/indexing/input → output/ (PIPELINE_TYPE=auto)
make index           # requires *.pipeline.json in tkeir/tests/indexing/output
make rag        # start FastAPI RAG API
make rag-query  # curl sample RAG request
make clean-db   # wipe Vespa data volume (then run make bootstrap)
```

## CLI entry points (from tkeir/)

Equivalent `python -m` modules (used by `vespa/Makefile`):

| CLI | Module |
|---|---|
| `tkeir-pipeline` | `thot.tools.pipeline` |
| `tkeir-index-documents` | `thot.tools.search.index_documents` |
| `tkeir-rag` | `thot.tools.search.app` |
| `tkeir-init-vespa` | `thot.tools.search.init_vespa` |
| `tkeir-create-annotation-resource` | `thot.tools.annotation.create_annotation_resource` |
