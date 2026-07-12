# Tools Overview

## Unified pipeline

T-KEIR analysis runs as a single in-process pipeline. Each step enriches one JSON document with tokens, morphosyntax, named entities, syntax, triples, and keywords.

```shell
tkeir-pipeline -c tkeir/configs/pipeline.json -i <input file or directory> -o <output directory> -t auto
```

Use `-t raw` for plain text only; use `-t auto` (or `make pipeline` default) for PDFs and Office files.

From the source tree:

```shell
python3 -m thot.tools.pipeline -c tkeir/configs/pipeline.json -i <input> -o <output> -t auto
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
10. **golden-chunking** — retrieval-oriented chunks with context payloads

### Vespa indexing and RAG

After pipeline output is produced, index fixtures or your own JSON under
`tkeir/tests/indexing/` and start the RAG stack — see [Vespa RAG](vespa_rag.md).

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

`pipeline.json` references individual task configs under `tkeir/configs/` (converter, tokenizer, mstagger, nertagger, syntactic-tagger, keywords). See the tool-specific pages for configuration field descriptions.
