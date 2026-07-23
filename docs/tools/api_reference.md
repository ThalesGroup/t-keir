# Tools API reference

Public helpers in `thot/tools/`, `thot/core/`, and the **ops layer**
(`thot/action/`, `thot/audit/`, `thot/governor/`, `thot/ingest/`) use Google-style
docstrings. Each documented **Example** section is executed in CI via
`tests/unittests/TestAllDocExamples.py`.

All new public functions should include a runnable **Example** block. Coverage
of `>>>` prompts is enforced by `tests/unittests/TestDocExampleCoverage.py`.

Run example tests:

```bash
cd tkeir
uv run pytest tests/unittests/TestToolsDocExamples.py -q
uv run pytest tests/unittests/TestDocExampleCoverage.py tests/unittests/TestAllDocExamples.py -q
```

## Ops layer (action / audit / governor)

| Module | Documented examples include |
|---|---|
| `thot.action.models` | `ActionRecord.compute_record_hash`, `seal` |
| `thot.action.sink` | `InMemoryActionSink.append`, `list_by_correlation` |
| `thot.audit.verify` | `verify_hot_chain` |
| `thot.audit.worm_store` | `WormSegmentStore.write_segment` |
| `thot.audit.privacy` | `SubjectKeyStore.pseudonym`, `forget` |
| `thot.audit.report` | `build_report`, `render_html` |
| `thot.audit.s3_put` | `s3_settings_from_env` |
| `thot.governor.tokens` | `ActionTokenService.mint` / `verify` / `revoke` |
| `thot.governor.flags` | `RuntimeFlagsStore.set_kill`, `is_killed` |
| `thot.governor.approvals` | `ApprovalQueue.enqueue`, `decide` |

## Path resolution (`thot.core.TkeirPaths`)

| Function | Purpose |
|---|---|
| `package_root()` | `tkeir/` package directory |
| `configs_dir()` | Bundled JSON/YAML configs |
| `resources_dir(language)` | Tokenizer lexicons per language |
| `repo_root()` | Git repository root |
| `vespa_dir()` | `vespa/` deployment directory |
| `rag_prompts_path()` | RAG prompt YAML |
| `resolve_path(path)` | Expand paths relative to `tkeir/` |
| `resolve_tkeir_paths(cfg)` | Resolve `resources-base-path` in configs |
| `effective_resources_path(path, lang)` | Fallback to bundled resources |

## Pipeline CLI (`thot.tools.pipeline`)

| Function | Purpose |
|---|---|
| `_is_tkeir_document(path)` | Detect analyzed JSON inputs |
| `_collect_inputs(path)` | Expand file or directory to sorted file list |
| `main()` | Pipeline entry point (`tkeir-pipeline`) |

## User space (`thot.tools.search.user_space`)

| Function / constant | Purpose |
|---|---|
| `DEV_USER_SPACE` | Fixed principal `dev@tkeir` (P0 / auth off) |
| `decode_jwt_payload(token)` | Decode JWT claims (no signature verify) |
| `user_space_from_claims(payload)` | `preferred_username` → `email` → `sub` |
| `resolve_vespa_user_space(authorization, fallback=…)` | Bearer JWT → env → `dev@tkeir` |

## Vespa client (`thot.tools.search.vespa_client`)

| Function | Purpose |
|---|---|
| `sanitize_vespa_string(value)` | Strip illegal control characters |
| `strip_search_vector_payload(payload)` | Remove context tags from chunk payload |
| `chunk_embedding_text(chunk)` | Text used for chunk embedding |
| `stable_document_key(source_doc_id)` | Hash key for parent documents |
| `document_vespa_id(source_doc_id, user_space=…)` | Parent id with streaming group |
| `chunk_vespa_id(chunk_id, user_space=…)` | Chunk id with streaming group |
| `normalize_user_space(…)` | Sanitize `VESPA_USER_SPACE` / group name |
| `build_chunk_tensor(vector, dim)` | Truncate embedding for schema |
| `build_questions_tensor(vectors, dim)` | Mapped tensor for question embeddings |
| `escape_yql_literal(query)` | Escape user text for YQL |

## Ontology utilities (`thot.tools.search.ontology_utils`)

| Function | Purpose |
|---|---|
| `merge_turtle_graphs(documents)` | Merge parent RDF graphs |
| `merge_rdf_graphs(documents)` | Merge JSON-LD / Turtle parent payloads |
| `build_hmi_ontology(...)` | Export entities + keywords + fused `json_ld` (+ merge counts) |
| `extract_relevant_triples(graph, query)` | Filter triple lines by query terms |
| `summarize_graph_for_prompt(graph, query)` | Bullet summary for LLM prompts |

## Ontology reasoner (`thot.tools.search.ontology_reasoner`)

| Helper | Role |
|--------|------|
| `query_merged_ontology` | SPARQL / subclasses / instances / types / consistency on fused JSON-LD |
| `owlapy_available` | Optional `owlapy` (`uv sync --extra owl`, Python ≥ 3.11) |

HTTP: `POST /rag/ontology/query` — examples in [Vespa RAG](vespa_rag.md).

## RAG app helpers (`thot.tools.search.app`)

| Function | Purpose |
|---|---|
| `_unavailable_answer(cfg, language)` | Localized no-answer message |
| `_no_chunks_message(cfg)` | Empty-retrieval prompt fragment |
| `_format_chunk_excerpts(chunks, empty_message)` | Chunk block for LLM |
| `_parse_hits(response)` | Parse Vespa search JSON |

## LLM wrapper (`thot.core.LlmWrapper`)

| Function / class | Purpose |
|---|---|
| `WrapperConfig.from_env()` | Build config from environment |
| `UnifiedLLMWrapper` | Provider-agnostic embed + generate client |

## Annotation tools (`thot.tools.annotation`)

| Command | Purpose |
|---|---|
| `tkeir-create-annotation-resource` | Build `tkeir_mwe.pkl` from lexicon JSON |

## Agent service (`thot.agent.service`) — CLI `tkeir-agent`

| Endpoint / symbol | Purpose |
|---|---|
| `POST /agent/runs` | Enqueue `RunState` (returns `run_id`, `spiffe_id`, `user_space`) |
| `GET /agent/runs/{run_id}` | Poll run + steps |
| `POST /agent/runs/{run_id}/cancel` | Request cancel |
| `POST /agent/runs/{run_id}/publish` | Approval-gated publish |
| `GET /ready` | Lists agents/workflows + `spiffe_id` |

### Classes (`thot.agent.models`)

| Field (RunState) | Type | Description |
|---|---|---|
| `run_id` | `str` | ULID |
| `agent` / `workflow` | `str` | Spec names |
| `user_space` | `str` | Vespa streaming group |
| `spiffe_id` | `str \| None` | Workload SPIFFE ID (ADR-0008) |
| `status` | Literal | `queued`…`killed` |
| `budgets` / `usage` | models | Token / tool / wall limits |

Example (from docstring CI):

```python
>>> from thot.agent.spiffe import synthesize_dev_spiffe_id
>>> synthesize_dev_spiffe_id("researcher")
'spiffe://tkeir.local/agent/researcher'
```

## SPIFFE helpers (`thot.agent.spiffe`)

| Function | Parameters | Returns | Description |
|---|---|---|---|
| `resolve_agent_spiffe_id` | `agent_name` | `str \| None` | Env / file / Workload API / `dev` synthesize |
| `require_agent_spiffe_id` | `agent_name` | `str` | Enforced allow-listed ID |
| `is_allowed_agent_spiffe_id` | `spiffe_id` | `bool` | Prefix allow-list check |

## Document ontology derivation (`thot.tasks.document_ontology.OntologyDerivation`)

| Function | Parameters | Returns | Description |
|---|---|---|---|
| `load_reference_graph` | `paths` | `Graph` | Load/merge TTL/OWL references |
| `derive_document_graph` | `doc`, `ref`, `settings` | `(Graph, report)` | Add subclass/type/sameAs links |
| `parse_derivation_settings` | `raw` | `DerivationSettings` | Parse `derive-from` YAML |

See [Document ontology](document_ontology.md) and [Architecture data model](../architecture/data-model.md).

## Ingest API (`thot.ingest.app`) — CLI `tkeir-ingest`

| Endpoint | Purpose |
|---|---|
| `POST /ingest/document` | Accept one document |
| `POST /ingest/batch` | Accept batch |
| `GET /ingest/status/{ingest_id}` | Job status |

### Key classes (`thot.ingest.models`)

| Class | Notable fields |
|---|---|
| `IngestManifest` | `doc_id`, `pipeline_config_sha256`, `embedder`, `lineage` |
| `IngestJob` | `status`, `correlation_id` |
| `DocumentIngestRequest` | request body for single ingest |

## RAG API (`thot.tools.search.app`) — CLI `tkeir-rag`

| Endpoint | Purpose |
|---|---|
| `POST /search` | Hybrid Vespa search |
| `POST /rag/query` | Full RAG answer path |
| `GET /health` `/ready` `/metrics` | Ops |

Run example tests:

```bash
cd tkeir
uv run pytest tests/unittests/TestToolsDocExamples.py -q
```
