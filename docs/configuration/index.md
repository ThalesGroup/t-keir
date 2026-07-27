# Configuration reference

All runtime YAML under `tkeir/configs/` is described here.  
**Source of truth for field semantics** is this section plus the linked tool pages.  
Eval harnesses (for example `make beir-smoke`) must **consume** these files; they must not invent parallel ranking strategy.

## Inventory

| File | Role | Detailed reference |
|------|------|-------------------|
| [`rag.yaml`](rag.yaml.md) | RAG API, Vespa endpoints, models, passage retrieval (`dual_hybrid:`) | **[Full field + algorithm reference](rag.yaml.md)** |
| [`rag-prompts.yaml`](rag.yaml.md#rag-promptsyaml) | Prompt templates for generation | [rag.yaml.md § prompts](rag.yaml.md#rag-promptsyaml) |
| [`pipeline.yaml`](pipeline.yaml.md) | NLP pipeline step map | **[pipeline.yaml](pipeline.yaml.md)** |
| `converter.yaml` | MarkItDown / raw conversion | [Converter](../tools/converter.md) |
| `tokenizer.yaml` / `tokenizer-mwe.yaml` | Segmentation + MWE tries | [Tokenizer](../tools/tokenizer.md) |
| `mstagger.yaml` | Morphosyntax | [MS tagger](../tools/mstagger.md) |
| `nertagger.yaml` | Named entities | [NER](../tools/nertagger.md) |
| `syntactic-tagger.yaml` | Dependencies / SVO | [Syntactic tagger](../tools/syntactictagger.md) |
| `keywords.yaml` | Keyword extraction | [Keywords](../tools/keywords.md) |
| `golden-chunking.yaml` | Chunk boundaries for index | [Vespa RAG](../tools/vespa_rag.md) |
| `document-ontology.yaml` | Document RDF / JSON-LD tagging | [Document ontology](../tools/document_ontology.md) |
| `chunk-questions.yaml` | Question generation per chunk | [Vespa RAG](../tools/vespa_rag.md) |
| [`mcp.yaml` / `mcp-client.yaml`](mcp.yaml.md) | MCP server / client | **[mcp.yaml](mcp.yaml.md)** + [MCP](../tools/mcp.md) |
| `agents/*.yaml` | Agent role prompts & tools | [Agents](../tools/agents.md) |
| `workflows/*.yaml` | Multi-agent workflows | [Agents](../tools/agents.md) |
| `templates/*.yaml` | Synthesis / profile templates | [Templates](../tools/templates.md) |

Business ontologies used at **query time** are **not** stored under `configs/`; they are request payloads (see [Datasets & ontologies](../tools/datasets.md)).

## Design rules

1. **No language-specific word lists in code.** Morphology / stopwords come from spaCy models selected by `dual_hybrid.preprocessing.spacy_models`. Synonyms come from the per-request `business_ontology`.
2. **Schema generation.** `dual_hybrid.rank_profiles` and `average_field_length` feed `make schemas` → `vespa/vespa_app/schemas/*.sd`. Do not hand-edit generated `.sd` files.
3. **Override order** (highest wins) for models and Vespa endpoints is documented in [`rag.yaml`](rag.yaml.md#override-order).
4. **Evaluation** (`make beir-smoke`, `make beir-eval`) loads production `rag.yaml`. Smoke may only clamp hits to corpus size and set eval `top_k`; it must not retune fusion weights.

## Related runbooks

- [Passage schema migration](../runbooks/dual-hybrid-migration.md)
- [Evaluation](../evaluation.md)
