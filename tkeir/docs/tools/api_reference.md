# Tools API reference

Public helpers in `thot/tools/` and `thot/core/TkeirPaths.py` use Google-style
docstrings. Each documented **Example** section is executed in
`tests/unittests/TestToolsDocExamples.py`.

All functions under `thot/` must include a runnable **Example** block in their
Google-style docstring. Coverage is enforced by
`tests/unittests/TestDocExampleCoverage.py`, and every example is executed via
doctest in `tests/unittests/TestAllDocExamples.py`.

Run example tests:

```bash
cd tkeir
uv run pytest tests/unittests/TestToolsDocExamples.py -q
uv run pytest tests/unittests/TestDocExampleCoverage.py tests/unittests/TestAllDocExamples.py -q
```

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

## Vespa client (`thot.tools.search.vespa_client`)

| Function | Purpose |
|---|---|
| `sanitize_vespa_string(value)` | Strip illegal control characters |
| `strip_search_vector_payload(payload)` | Remove context tags from chunk payload |
| `chunk_embedding_text(chunk)` | Text used for chunk embedding |
| `stable_document_key(source_doc_id)` | Hash key for parent documents |
| `document_vespa_id(source_doc_id)` | Vespa parent document id |
| `chunk_vespa_id(chunk_id)` | Vespa chunk document id |
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
