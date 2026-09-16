# Configuration reference

All runtime YAML under `tkeir/configs/` is described here.
**Source of truth for field semantics** is this section (what each key *does*
when you change it) plus the linked tool pages.

Eval harnesses (for example `make beir-smoke`) must **consume** these files;
they must not invent parallel ranking strategy.

## How to read the tables

Each detailed page lists **field → default → effect**. Fields marked
**reserved** are parsed or present in YAML but not consumed by the current
runtime — changing them has no effect until code starts reading them.

Shared `logger.logging-level` (`debug` … `critical`) only changes log
verbosity for that process.

## Inventory

### Pipeline, search, MCP

| File | Role | Field-by-field reference |
|------|------|--------------------------|
| [`rag.yaml`](rag.yaml.md) | RAG API, Vespa, models, `dual_hybrid:` | **[rag.yaml](rag.yaml.md)** |
| [`rag-prompts.yaml`](rag.yaml.md#rag-promptsyaml) | `/rag/query` generation strings | [rag.yaml.md § prompts](rag.yaml.md#rag-promptsyaml) · [agents.yaml.md](agents.yaml.md#rag-promptsyaml) |
| [`pipeline.yaml`](pipeline.yaml.md) | NLP step map (filenames only) | **[pipeline.yaml](pipeline.yaml.md)** |
| [`mcp.yaml` / `mcp-client.yaml`](mcp.yaml.md) | MCP server bind + outbound egress | **[mcp.yaml](mcp.yaml.md)** |

### NLP tasks (selected by `pipeline.yaml`)

| File | Role | Field-by-field reference |
|------|------|--------------------------|
| `converter.yaml` | MarkItDown / OCR / captions | **[NLP YAML](nlp.yaml.md#converteryaml)** · [Converter](../tools/converter.md) |
| `tokenizer.yaml` | Segmentation + MWE | **[NLP YAML](nlp.yaml.md#tokenizeryaml--tokenizer-mweyaml)** · [Tokenizer](../tools/tokenizer.md) |
| `tokenizer-mwe.yaml` | Same schema, quieter logs; **not** wired in `pipeline.yaml` | [NLP YAML](nlp.yaml.md#tokenizeryaml--tokenizer-mweyaml) |
| `mstagger.yaml` | POS / lemmas | **[NLP YAML](nlp.yaml.md#mstaggeryaml-morphosyntax)** · [MS tagger](../tools/mstagger.md) |
| `nertagger.yaml` | Named entities | **[NLP YAML](nlp.yaml.md#nertaggeryaml)** · [NER](../tools/nertagger.md) |
| `syntactic-tagger.yaml` | Dependencies / SVO | **[NLP YAML](nlp.yaml.md#syntactic-taggeryaml)** · [Syntactic tagger](../tools/syntactictagger.md) |
| `keywords.yaml` | RAKE keywords | **[NLP YAML](nlp.yaml.md#keywordsyaml)** · [Keywords](../tools/keywords.md) |

### Index path

| File | Role | Field-by-field reference |
|------|------|--------------------------|
| `golden-chunking.yaml` | Chunk size / NER-density split | **[Indexing YAML](indexing.yaml.md#golden-chunkingyaml)** |
| `document-ontology.yaml` | Document RDF, alignment, derive-from | **[Indexing YAML](indexing.yaml.md#document-ontologyyaml)** · [Document ontology](../tools/document_ontology.md) |
| `chunk-questions.yaml` | Synthetic questions on chunks (not Vespa-ranked) | **[Indexing YAML](indexing.yaml.md#chunk-questionsyaml)** |

### Agents, collector

| File | Role | Field-by-field reference |
|------|------|--------------------------|
| `agents/*.yaml` | Role prompts, tools, budgets, OKF wiki fields | **[Agents YAML](agents.yaml.md)** · [Agents](../tools/agents.md) |
| `workflows/*.yaml` | Multi-agent plans + compose | **[Agents YAML](agents.yaml.md)** · [Agents](../tools/agents.md) |
| `templates/*.yaml` | Compose slots + markdown | **[Agents YAML](agents.yaml.md)** · [Templates](../tools/templates.md) |
| `collector/osint_sources.yaml` | Host allowlist | **[Collector YAML](collector.yaml.md)** |
| `collector/topics.yaml` | `topic` → business ontology dataset | **[Collector YAML](collector.yaml.md#topicsyaml)** |
| `collector/forge.yaml` | Query forge / geocode / NLP seeds | **[Collector YAML](collector.yaml.md#forgeyaml)** |

Usecase packs (`datasets/osint/hmi.json`, `keycloak.json`,
`agent_orchestrator.yaml`, persona agents) are **not** under `tkeir/configs/`.
Contract: [Create a usecase pack](../tools/usecase.md) (OSINT walkthrough).

Business ontologies used at **query time** are request payloads, not
`tkeir/configs/` files — see [Datasets & ontologies](../tools/datasets.md).

## Design rules

1. **No language-specific word lists in code.** Morphology / stopwords come from spaCy models selected by `dual_hybrid.preprocessing.spacy_models`. Synonyms come from the per-request `business_ontology`.
2. **Schema generation.** `dual_hybrid.rank_profiles` and `average_field_length` feed `make schemas` → `vespa/vespa_app/schemas/*.sd`. Do not hand-edit generated `.sd` files.
3. **Override order** (highest wins) for models and Vespa endpoints is documented in [`rag.yaml`](rag.yaml.md#override-order).
4. **Evaluation** (`make beir-smoke`, `make beir-eval`) loads production `rag.yaml`. Smoke may only clamp hits to corpus size and set eval `top_k`; it must not retune fusion weights.

## Related runbooks

- [Passage schema migration](../runbooks/dual-hybrid-migration.md)
- [Evaluation](../evaluation.md)
