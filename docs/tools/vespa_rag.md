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

Default index input: `tests/indexing/output`.

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

**Preferred answer path:** agent workflow `rag_with_wiki`
(`search_chunks` → `wiki_upsert` → `answer_generate`) on `:8092`.
Legacy `POST /rag/query` may still generate in-process; optional fields
`use_wiki` / `wiki_extract` / `agent_id` / `answer_template` forward wiki
context or audit metadata (template fill remains agent-owned).
Set `stop_at_wiki_extract=true` with `use_wiki` to skip answer generation
and return the wiki extract (plus chunks) only.

### `POST /documents/analyze` (NLP only)

Multipart upload → converter + full pipeline → analyzed document JSON.
Does **not** write to Vespa. Default converter datatype is **`raw`**
(UTF-8 plain text via `RawTextConverter`).

Optionally upload a `business_ontology.yaml` as a second multipart file;
matched concepts are annotated after NLP.

```bash
curl -sS -X POST "http://localhost:8090/documents/analyze" \
  -F "file=@./notes.txt;type=text/plain" \
  -F "datatype=raw" \
  -F "language=en" \
  -F "business_ontology=@datasets/osint/business_ontology.yaml"
```

| Form field | Default | Notes |
|---|---|---|
| `file` | required | Document bytes |
| `datatype` | `raw` | Converter type (`raw`, `auto`, `pdf`, …) |
| `language` | `en` | Selects preloaded pipeline runner |
| `business_ontology` | unset | Multipart YAML/JSON file (`business_ontology.yaml`) |

Response is the full pipeline output (`content`, `golden_chunks`, NER, …),
plus BO annotations on `document_ontology` / `kg` / `core_concepts` when applied.
