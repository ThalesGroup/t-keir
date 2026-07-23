# Vespa search and RAG

T-KEIR uses a two-level Vespa stack for hybrid retrieval in **streaming mode**
(per-user / tenant document spaces):

- **Parent `tkeir_document`** — BM25 on title and content, stores document
  ontology as **`json_ld`** (plus `shacl_status`)
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
(`make clean-db` then `make bootstrap`). Text fields used with `bm25()` must be
declared as `indexing: summary | index` with `index: enable-bm25` — do **not**
mix `attribute` on those fields or deploy fails with “Expected field to be an
index field”. Streaming has no corpus term stats; rank profiles set
`bm25(...).averageFieldLength` explicitly.
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
| `ontology` | **Merged** parent ontologies from Vespa (see below) |
| `vespa_hits` | Raw Vespa hit count before enrichment |
| `ranking_profile` | Vespa ranking profile used when known |

Document score: `max(chunk_score) + 0.05 * log1p(hit_count)`.

### Merged ontology (search + RAG)

After hybrid search, the API fetches each hit’s parent document and unions the
`json_ld` fields into one RDF graph (`merge_rdf_graphs` /
`build_hmi_ontology`):

| Field | Description |
|---|---|
| `entities` | NER-style labels with linked `chunk_ids` |
| `keywords` | Keyword labels with linked `chunk_ids` |
| `json_ld` | Fused graph (JSON-LD) for HMI display and reasoner follow-ups |
| `triple_count` | Number of RDF triples in the merge |
| `source_count` | Unique parent ontology payloads merged |
| `document_ids` | Parent `source_doc_id` values that contributed |

The HMI **Ontology Navigator** shows entities, keywords, JSON-LD, and a
**Reason** tab that posts the fused `json_ld` to `/rag/ontology/query`.

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
| `ontology` | Same merged ontology shape as `/search` (entities, keywords, `json_ld`, counts) |
| `vespa_hits` | Raw Vespa hit count |

Prompt templates: `tkeir/configs/rag-prompts.yaml` (`unavailable_answer` per language).

### `POST /rag/ontology/query` (reasoner / SPARQL on fused ontology)

Interact with the **merged ontology returned by the initial search/RAG call**
(pass `ontology.json_ld` from that response). Optional **OWLAPY** SyncReasoner
(HermiT, Pellet, ELK, …) when installed; otherwise rdflib SPARQL / RDFS walks.

```bash
# Optional Java reasoners (JPype / OWLAPI)
cd tkeir && uv sync --extra owl
```

**Example — after a RAG answer, list subclasses:**

```bash
# 1) Initial RAG query (stores fused ontology in the response)
curl -s http://localhost:8090/rag/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"SITREP Objective ALPHA","language":"en","hits":10}' \
  > /tmp/rag.json

# 2) Extract fused JSON-LD and ask for subclasses of a class IRI
JSON_LD=$(python3 -c 'import json; print(json.load(open("/tmp/rag.json"))["ontology"]["json_ld"])')
curl -s http://localhost:8090/rag/ontology/query \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg j "$JSON_LD" \
    '{json_ld:$j, operation:"subclasses",
      class_iri:"http://tkeir.local/ontology/Organization",
      reasoner:"HermiT", limit:50}')" | jq .
```

**Example — SPARQL over the merge (always available via rdflib):**

```bash
curl -s http://localhost:8090/rag/ontology/query \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg j "$JSON_LD" \
    --arg q 'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?label WHERE { ?s rdfs:label ?label } LIMIT 20' \
    '{json_ld:$j, operation:"sparql", sparql:$q}')" | jq .
```

**Example — instances of a class / types of an individual:**

```bash
# Individuals typed as a class
curl -s http://localhost:8090/rag/ontology/query \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg j "$JSON_LD" \
    '{json_ld:$j, operation:"instances",
      class_iri:"http://tkeir.local/ontology/Organization"}')" | jq .

# Named types of one individual
curl -s http://localhost:8090/rag/ontology/query \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg j "$JSON_LD" \
    '{json_ld:$j, operation:"types",
      individual_iri:"http://tkeir.local/doc/e1"}')" | jq .
```

| `operation` | Needs | Backend |
|-------------|-------|---------|
| `sparql` | `sparql` SELECT | rdflib |
| `subclasses` / `superclasses` | `class_iri` | OWLAPY if installed, else RDFS walk |
| `instances` | `class_iri` | OWLAPY / rdflib |
| `types` | `individual_iri` | OWLAPY / rdflib |
| `consistency` | — | OWLAPY HermiT (preferred) |
| `infer` | — | OWLAPY (`InferredClassAssertionAxiomGenerator`) |

Response: `{ operation, backend, reasoner, results[], count, triple_count, owlapy_available, json_ld, note? }`.

The HMI **Reason** tab lets you pick the reasoner (`rdflib`, HermiT, Pellet, …),
runs the query, and shows the answer as a **graph** (from `json_ld`) or raw
JSON-LD.

Implementation: `thot.tools.search.ontology_reasoner.query_merged_ontology`.

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
