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
| `build_hmi_ontology(turtles, chunk_ids, chunk_texts)` | Export entities + keywords for HMI |
| `extract_relevant_triples(graph, query)` | Filter triple lines by query terms |
| `summarize_graph_for_prompt(graph, query)` | Bullet summary for LLM prompts |

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

Run example tests:

```bash
cd tkeir
uv run pytest tests/unittests/TestToolsDocExamples.py -q
```
