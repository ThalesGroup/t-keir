# Vespa search and RAG

T-KEIR uses two Vespa schemas sharing `doc_base`:

- **`global`** — index-mode catalog (HNSW dense ANN) for shared corpora (e.g. BEIR)
- **`user`** — streaming-mode per-tenant passages (`userspace_id` + `streaming.groupname`)

Both store BGE-M3 **dense** (1024-d) + **sparse** tensors, BM25 on `chunk_text`,
and `ontology_concepts`. Runtime search is
`thot.tools.search.passage_retrieval.PassageRetrievalPipeline` (modes:
`global` | `user` | `both` | `auto`). When `search.enabled` in `rag.yaml`,
each query runs the T-KEIR linguistic pipeline (NER / lemmas / keywords)
before BGE-M3 embed and Vespa hybrid search — including BEIR smoke/eval.

Python tooling: **`thot/tools/ingest/`** (index), **`thot/tools/search/`**
(retrieval / RAG), **`thot/tools/eval/`** (BEIR). Docker schemas and scripts live in
`vespa/` at the repository root.

## User space (streaming group)

| Mode | User space |
|------|------------|
| **Keycloak** (Bearer on `/search`, `/rag/query`, ingest) | `preferred_username` → `email` → `sub` |
| **Dev / auth off** | `dev@tkeir` (or `VESPA_USER_SPACE` override) |

| Setting | Source |
|---------|--------|
| Global id | `id:default:global::<digest>` |
| User id | `id:default:user:g=<space>:<digest>` |
| Feed API (user) | `/document/v1/.../group/<space>/<key>` |
| Query (user) | JSON field `streaming.groupname` |

**Migration:** schema changes require a clean Vespa volume
(`make clean-db` then `make bootstrap`) and re-index.

## Quick start

```bash
# From repository root
make install
make bootstrap
make index-fixtures   # optional: build indexing fixtures from PDFs
make index
make rag
make rag-query RAG_QUERY="your question"
make search-query RAG_QUERY="your question"   # retrieval only
```

## Web UI (tkeir-hmi)

```bash
cd tkeir-hmi && npm install && npm run dev
```

See [HMI documentation](../hmi.md).

Default index input: `tkeir/tests/indexing/output`.

## CLI entry points

| Command | Module |
|---|---|
| `tkeir-init-vespa` | `thot.tools.search.init_vespa` |
| `tkeir-index-documents` | `thot.tools.ingest.index_documents` (→ `index_passages`) |
| `tkeir-rag` | `thot.tools.search.app` |

## RAG API

### `POST /search` (retrieval only)

Hybrid Vespa search + optional second-stage rerank. No LLM answer generation.

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
| `chunks` | Reranked passages with ids, text, parent ref, score |
| `documents` | Documents aggregated from those passages |
| `vespa_hits` | Raw Vespa hit count before enrichment |
| `ranking_profile` | Vespa ranking profile used when known |

Schemas are generated from `tkeir/configs/rag.yaml` via `make schemas`.
