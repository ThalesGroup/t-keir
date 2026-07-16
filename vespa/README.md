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
export RERANKER_MODEL=qllama/bge-reranker-v2-m3
make pull-models      # ollama pull embedding + llm + reranker
make index-fixtures   # PDFs in tkeir/tests/indexing/input → output/
make index

# 4. Run the FastAPI RAG API
make rag

# 5. Sample query
make rag-query RAG_QUERY="Who is Rob Brown?"
```

Default indexing input: `tkeir/tests/indexing/output` (override with `INDEX_INPUT`).

## Environment variables

Model settings resolve as **environment → `configs/rag.yaml` `models:` → hard-coded defaults**.

| Variable | Default | Purpose |
|---|---|---|
| `PROVIDER` | `ollama` | `openai`, `ollama`, or `vllm` |
| `EMBEDDING_MODEL` | provider-specific / `rag.yaml` | Embedding model name |
| `LLM_MODEL` | provider-specific / `rag.yaml` | Generation model name |
| `RERANKER_MODEL` | `qllama/bge-reranker-v2-m3` | Reranker model (native `/rerank` if present, else generate/chat scoring; falls back to `LLM_MODEL`) |
| `EMBEDDING_DIM` | `384` | Embedding dimension (must match schemas) |
| `VESPA_URL` | `http://localhost:8080` | Vespa endpoint |
| `VESPA_NAME` | `vespa` | Docker container name |
| `VESPA_VOLUME` | `vespa_data:/opt/vespa/var` | Docker volume mount for Vespa data |
| `BEIR_DATASETS_DIR` | `<repo>/datasets` | Cache for BEIR dataset downloads |
| `BEIR_REPORT` | `<repo>/evaluation_report.md` | BEIR Markdown evaluation report path |
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
make sync        # uv sync in tkeir/
make pull-models # ollama pull embedding + llm + reranker (env / rag.yaml)
make start       # docker run Vespa
make init        # deploy schemas (Vespa already running)
make bootstrap   # start + deploy schemas
make check       # health check
make test        # Vespa query smoke test
make test-py     # Python unit tests (tkeir)
make index-fixtures  # pipeline on tkeir/tests/indexing/input → output/ (PIPELINE_TYPE=auto)
make index           # requires *.pipeline.json in tkeir/tests/indexing/output
make rag         # FastAPI RAG (hybrid retrieval + Ollama rerank when enabled)
make rag-query   # curl sample RAG request
make clean-db    # wipe Vespa data volume (then run make bootstrap)
make beir-eval   # BEIR BM25 + dense eval → evaluation_report.md
```

## BEIR evaluation

```bash
cd vespa
# Full benchmark: T-KEIR pipeline + local BM25/dense vs BEIR leaderboard
make beir-eval

# Offline baselines only (no Vespa / embeddings):
make beir-eval BEIR_EXTRA=--skip-tkeir

# SciFact smoke (skip MiniLM dense, keep T-KEIR):
make beir-eval BEIR_DATASETS=scifact BEIR_EXTRA=--skip-dense

# Fast index smoke (no document NLP; useful if chunking looks stalled):
make beir-eval BEIR_DATASETS=scifact \
  BEIR_EXTRA='--skip-dense --tkeir-index-mode fast --tkeir-max-docs 50'
```

Default T-KEIR index mode is `--tkeir-index-mode chunking` (NLP through
chunking + structural questions). Avoid `--tkeir-index-mode full` for large
corpora — that pulls ontology via `chunk-questions` and can stall for hours
with little progress logging.

Downloads SciFact / FiQA / ArguAna into `./datasets/` (if missing), then:

1. **T-KEIR (retrieval only)** — NLP (`chunking` + structural question
   projections) → embed/index → `QueryAnalyzerTask` + Vespa hybrid →
   optional cross-encoder rerank via `UnifiedLLMWrapper.rerank`
   (`RERANKER_MODEL` / `search.rerank` in `rag.yaml`).
   **No answer generation** (`RetrievalEmbeddingClient` rejects `generate`)
2. **Local BM25** / **Local dense** — in-process baselines for contrast
3. Metrics NDCG@10 / MAP@100 / Recall@100 + **gap to best published** system
4. Writes `evaluation_report.md` with leaderboard comparison

Requires a working embedding + (when enabled) rerank provider
(`PROVIDER` / `EMBEDDING_MODEL` / `RERANKER_MODEL` / `OLLAMA_BASE_URL`) and
spaCy models. Prefetch with `make pull-models`. Rerank prefers native
`/api/rerank` / `/v1/rerank` / OpenAI-compat `/rerank`, then scores via
standard Ollama `/api/generate` or OpenAI/vLLM chat completions (auto-falls
back to `LLM_MODEL` if the pulled cross-encoder cannot run as generate).
Reindex uses volume `beir_eval_data` by default — set `BEIR_VESPA_VOLUME` /
`BEIR_VESPA_NAME` to isolate from your primary corpus. Redeploy Vespa after
schema changes:

```bash
cd vespa && make clean-db && make bootstrap
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
