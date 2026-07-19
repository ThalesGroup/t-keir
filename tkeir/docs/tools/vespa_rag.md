# Vespa search and RAG

T-KEIR uses a two-level Vespa stack for hybrid retrieval in **streaming mode**
(per-user / tenant document spaces):

- **Parent `tkeir_document`** — BM25 on title and content, stores ontology Turtle
- **Child `chunk`** — exact nearest-neighbor on chunk / question tensors + BM25

Streaming mode co-locates each user's documents via the Vespa **group** in the
document id (`g=<user_space>`). Searches must set `streaming.groupname` to that
same space so one user never scans another user's corpus.

Python tooling lives in `thot/tools/search/`. Docker schemas and scripts live in
`vespa/` at the repository root.

## User space (streaming group)

| Mode | User space |
|------|------------|
| **Keycloak** (Bearer on `/search`, `/rag/query`, ingest) | `preferred_username` → `email` → `sub` |
| **Dev / auth off** | `dev@tkeir` (or `VESPA_USER_SPACE` override) |

HMI already forwards the Auth.js access token as `Authorization: Bearer …`,
so each signed-in Keycloak user searches/indexes their own Vespa group.

| Setting | Source |
|---------|--------|
| Document id | `id:default:chunk:g=<space>:<key>` |
| Feed API | `/document/v1/.../group/<space>/<key>` |
| Query | JSON field `streaming.groupname` |

P0 without login uses `dev@tkeir` for a single local corpus. Multi-tenant /
personal indexes come from Keycloak at request time.

**Migration:** switching from indexed → streaming requires a clean Vespa volume
(`vespa/clean_db.sh`) then `make bootstrap` and re-index.

## Quick start

```bash
# From repository root — indexes into g=dev@tkeir by default
make install
make bootstrap
make index-fixtures   # optional: build indexing fixtures from PDFs
make index
make rag
make rag-query RAG_QUERY="your question"
make search-query RAG_QUERY="your question"   # retrieval only (chunks + documents)
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
| `tkeir-index-documents` | `thot.tools.search.index_documents` |
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
| `chunks` | Reranked chunks with `chunk_id`, `text_raw`, `parent_doc_id`, `score`, `title` |
| `documents` | Documents aggregated from those chunks (`document_id`, `score`, `chunk_ids`, `title`, `hit_count`) |
| `vespa_hits` | Raw Vespa hit count before enrichment |
| `ranking_profile` | Vespa ranking profile used when known |

Document score: `max(chunk_score) + 0.05 * log1p(hit_count)`.

### `POST /rag/query` (retrieval + generation)

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

## Configuration (`tkeir/configs/rag.yaml`)

Runtime settings for models, search/rerank, prompts, ontology, and Vespa:

```yaml
vespa:
  url: http://localhost:8080
  config_url: http://localhost:19071
  timeout_seconds: 60
  user_space: "dev@tkeir"   # auth-off fallback; live requests use Keycloak JWT
  concurrency:
    index_workers: 2      # parallel pipeline JSON files (embeds still serial)
    chunk_workers: 4      # parallel Vespa chunk upserts
    query_workers: 1      # BEIR multi-query stays sequential
    enrich_workers: 8     # parallel parent-document fetches after search
```

**Concurrency caveats:** embedding calls are process-wide serialized (local
Ollama/vLLM stalls under parallel embed). BEIR index and retrieve always run
one document/query at a time because they share a single NLP pipeline.
Environment variables still override YAML for endpoints and timeout
(`VESPA_URL`, `VESPA_CONFIG_URL`, `VESPA_TIMEOUT_SECONDS`).

Indexing CLI: `tkeir-index-documents -i DIR [--workers N]` (defaults to
`vespa.concurrency.index_workers`).

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PROVIDER` | `ollama` | `openai`, `ollama`, or `vllm` |
| `EMBEDDING_MODEL` | provider-specific | Embedding model |
| `LLM_MODEL` | provider-specific | Generation model |
| `EMBEDDING_DIM` | `384` | Must match Vespa schemas |
| `VESPA_URL` | from `rag.yaml` / `http://localhost:8080` | Vespa search API |
| `VESPA_CONFIG_URL` | from `rag.yaml` / `http://localhost:19071` | Vespa config server |
| `VESPA_TIMEOUT_SECONDS` | from `rag.yaml` / `60` | HTTP timeout |
| `VESPA_USER_SPACE` | `dev@tkeir` | Auth-off / CLI fallback streaming group |
| `RAG_PORT` | `8090` | FastAPI bind port |
| `RAG_CORS_ORIGINS` | `http://localhost:3000,…` | CORS origins for direct HMI → API access |

`ontology.min_keyword_length` in `rag.yaml` filters single-letter keywords from
the HMI ontology export.

See also [API reference](api_reference.md) for documented Python helpers.
