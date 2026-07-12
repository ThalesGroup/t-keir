# Vespa search and RAG

T-KEIR uses a two-level Vespa stack for hybrid retrieval:

- **Parent `tkeir_document`** — BM25 on title and content, stores ontology Turtle
- **Child `chunk`** — HNSW vectors on chunk text and synthetic questions

Python tooling lives in `thot/tools/search/`. Docker schemas and scripts live in
`vespa/` at the repository root.

## Quick start

```bash
cd vespa
make sync
make bootstrap
make index-fixtures   # optional: build indexing fixtures from PDFs
make index
make rag
make rag-query RAG_QUERY="your question"
```

## Web UI (tkeir-hmi)

```bash
cd ../tkeir-hmi && npm install && npm run dev
```

See [HMI documentation](../hmi.md).

Default index input: `tkeir/tests/indexing/output`.

## CLI entry points

| Command | Module |
|---|---|
| `tkeir-init-vespa` | `thot.tools.search.init_vespa` |
| `tkeir-index-documents` | `thot.tools.search.index_documents` |
| `tkeir-rag` | `thot.tools.search.app` |

## RAG API

`POST /rag/query`

```json
{
  "query": "Who founded Acme?",
  "language": "en",
  "hits": 20
}
```

Response fields:

| Field | Description |
|---|---|
| `answer` | Short answer (1–3 sentences) grounded on retrieved chunks |
| `report_markdown` | Full downloadable markdown report (analysis, entities, sources) |
| `highlight_entities` | Top entity labels to highlight in the UI |
| `highlight_keywords` | Top keyword labels to highlight in the UI |
| `chunks` | Retrieved chunks with `chunk_id`, `text_raw`, `parent_doc_id`, `relevance` |
| `ontology` | Merged semantic view: `entities` (NER) and `keywords`, each with `chunk_ids` |
| `vespa_hits` | Raw Vespa hit count |

Prompt templates: `tkeir/configs/rag-prompts.yaml` (`unavailable_answer` per language).

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PROVIDER` | `ollama` | `openai`, `ollama`, or `vllm` |
| `EMBEDDING_MODEL` | provider-specific | Embedding model |
| `LLM_MODEL` | provider-specific | Generation model |
| `EMBEDDING_DIM` | `384` | Must match Vespa schemas |
| `VESPA_URL` | `http://localhost:8080` | Vespa search API |
| `RAG_PORT` | `8090` | FastAPI bind port |
| `RAG_CORS_ORIGINS` | `http://localhost:3000,…` | CORS origins for direct HMI → API access |

RAG runtime settings: `tkeir/configs/rag.yaml` (`ontology.min_keyword_length` filters
single-letter keywords from the HMI ontology export).

See also [API reference](api_reference.md) for documented Python helpers.
