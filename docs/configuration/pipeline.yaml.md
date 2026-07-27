# `pipeline.yaml` — configuration reference

Path: `tkeir/configs/pipeline.yaml`  
CLI: `tkeir-pipeline -c tkeir/configs/pipeline.yaml …`  
Module: `thot.tools.pipeline`

Orchestrates the in-process NLP enrichment chain. Each `configs.*` entry is a
**filename relative to `tkeir/configs/`** (or an absolute path).

## File schema

```yaml
logger:
  logging-level: info          # debug | info | warning | error
pipeline:
  default-language: en         # fallback when detection fails
  configs:
    converter: converter.yaml
    tokenizer: tokenizer.yaml
    morphosyntax: mstagger.yaml
    ner: nertagger.yaml
    syntax: syntactic-tagger.yaml
    keywords: keywords.yaml
    chunking: golden-chunking.yaml
    ontology: document-ontology.yaml
    chunk-questions: chunk-questions.yaml
```

| Field | Type | Description |
|-------|------|-------------|
| `logger.logging-level` | string | Process log level for the pipeline run |
| `pipeline.default-language` | string | ISO-ish language code used when detection is missing / low confidence |
| `pipeline.configs.converter` | path | Raw / PDF / Office → T-KEIR document ([Converter](../tools/converter.md)) |
| `pipeline.configs.tokenizer` | path | Tokens + MWE ([Tokenizer](../tools/tokenizer.md)) |
| `pipeline.configs.morphosyntax` | path | POS / lemmas ([MS tagger](../tools/mstagger.md)) |
| `pipeline.configs.ner` | path | Named entities ([NER](../tools/nertagger.md)) |
| `pipeline.configs.syntax` | path | Dependencies + SVO triples ([Syntactic tagger](../tools/syntactictagger.md)) |
| `pipeline.configs.keywords` | path | Keyword extraction ([Keywords](../tools/keywords.md)) |
| `pipeline.configs.chunking` | path | Golden / sliding chunks for Vespa index ([Vespa RAG](../tools/vespa_rag.md)) |
| `pipeline.configs.ontology` | path | Document JSON-LD / RDF tagging ([Document ontology](../tools/document_ontology.md)) |
| `pipeline.configs.chunk-questions` | path | Optional structural questions per chunk (NLP only; not indexed in Vespa) |

## Execution order

1. converter  
2. language detection (`langdetect`)  
3. resource selection (tokenizer trie by language)  
4. tokenizer → morphosyntax → ner → syntax → keywords  
5. ontology (optional derive-from upstream ontologies)  
6. chunking → chunk-questions (index path)

See [Tools overview](../tools/tools_overview.md) for CLI flags (`-t auto|raw`, `-i`, `-o`).

## Related

- Catalog: [Configuration overview](index.md)  
- Search / RAG after indexing: [rag.yaml](rag.yaml.md)
