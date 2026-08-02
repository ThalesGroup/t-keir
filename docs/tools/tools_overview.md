# Tools Overview

## Unified pipeline

T-KEIR analysis runs as a single in-process pipeline. Each step enriches one JSON document with tokens, morphosyntax, named entities, syntax, triples, and keywords.

```shell
tkeir-pipeline -c tkeir/configs/pipeline.yaml -i <input file or directory> -o <output directory> -t auto
```

Use `-t raw` for plain text only; use `-t auto` (or `make pipeline` default) for PDFs and Office files.

From the source tree:

```shell
python3 -m thot.tools.pipeline -c tkeir/configs/pipeline.yaml -i <input> -o <output> -t auto
```

### Pipeline steps

1. **converter** — raw text or office/PDF/HTML via MarkItDown into a T-KEIR document
2. **language-detection** — detected language and confidence (`langdetect`)
3. **resource-selection** — tokenizer trie path for the detected language (`None` when missing; processing falls back to `en` or `fr`)
4. **tokenizer** — `content_tokens` / `title_tokens`
5. **morphosyntax** — POS and lemmas
6. **ner** — named entities
7. **syntax** — dependencies and knowledge-graph triples
8. **keywords** — RAKE keywords
9. **ontology** — RDF graph serialization for downstream search/RAG
   (optional **derive-from** existing ontologies such as C2SIM — see
   [Document ontology](document_ontology.md))
10. **golden-chunking** — retrieval-oriented chunks with context payloads

### Vespa indexing and RAG

After pipeline output is produced, index fixtures or your own JSON under
`tests/indexing/` and start the RAG stack — see [Vespa RAG](vespa_rag.md).

### Agentic layer (MCP, agents, templates)

T-KEIR also exposes the indexed corpus to **agents** and external **MCP**
clients, and can **compose** grounded documents from the fused ontology.
Agents reuse the MCP *handlers* in-process; the `tkeir-mcp` service is only
needed for external MCP hosts (see [MCP](mcp.md)).

| Capability | Make / docs |
|---|---|
| MCP read-only tools (external clients) | `make mcp` — [MCP server](mcp.md) |
| Single-agent / workflows | `make agent`, `make workflow-run` — [Agents](agents.md) |
| Ontology templates | `make compose TEMPLATE=synthesis_note` — [Templates](templates.md) |
| HMI run monitor | `/agents` — [HMI](../hmi.md) |

Base agents ship as YAML under `tkeir/configs/agents/` (`researcher`,
`analyst`, `writer`, `reviewer`) plus dataset packs under
`datasets/<pack>/agents/` (OSINT personas). Workflows live under
`tkeir/configs/workflows/` and `datasets/<pack>/workflows/`. The runtime is
implemented in `thot/agent/` and `thot/mcp/` **without** third-party agent
frameworks; governance uses the same ActionRecord / governor path as ingest.

### Initialize tokenizer resources

Before the first run, build the multi-word expression pickle (`thot/tools/annotation/`):

```shell
tkeir-create-annotation-resource \
  --entries-file resources/modeling/tokenizer/en/annotation-resources.json \
  --output resources/modeling/tokenizer/en/tkeir_mwe.pkl
```

Or from source:

```shell
python3 -m thot.tools.annotation.create_annotation_resource \
  --entries-file resources/modeling/tokenizer/en/annotation-resources.json \
  --output resources/modeling/tokenizer/en/tkeir_mwe.pkl
```

### Per-task configuration

`pipeline.yaml` references individual task configs under `tkeir/configs/` (converter, tokenizer, mstagger, nertagger, syntactic-tagger, keywords). See the tool-specific pages for configuration field descriptions.

**Catalog of all config files:** [Configuration overview](../configuration/index.md).  
**RAG / passage retrieval (exhaustive):** [rag.yaml reference](../configuration/rag.yaml.md).
Packages: `thot.tools.ingest` (index), `thot.tools.search` (RAG), `thot.tools.eval` (BEIR).
