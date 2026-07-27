# Passage schema migration (`doc_base` / `global` / `user`)

T-KEIR no longer uses separate `tkeir_document` + `chunk` Vespa schemas.
Passages share **`doc_base`** (text / sparse / ontology) plus per-schema
`dense_vector` (HNSW on `global`, attribute-only on `user`) and are stored in:

| Schema | Mode | Role |
|--------|------|------|
| `global` | index (HNSW) | Shared catalog (BEIR, public corpora) |
| `user` | streaming | Per-tenant passages (`userspace_id`) |

Parent denormalization (`parent_title` / `parent_content`) and question
tensors (`questions_embeddings`) are gone.

## Prerequisites

1. Regenerate schemas from config:

   ```bash
   make schemas
   make schemas-check
   ```

2. Wipe and redeploy Vespa (streaming / schema changes are breaking):

   ```bash
   make clean-db
   make bootstrap
   ```

3. Ensure BGE-M3 weights are local (not Hugging Face hub cache):

   ```bash
   make pull-bge-model   # → tkeir/resources/modeling/net/bge-m3
   ```

## Reindex

Index **passages** (NLP `golden_chunks`) into `global` and/or `user`:

```bash
make index-fixtures   # optional: PDF → *.pipeline.json
make index            # thot.tools.ingest.index_documents → index_passages
```

BEIR smoke/eval force **`global` only**. Live RAG defaults to
`dual_hybrid.search_mode: auto` (`global` | `user` | `both`).

## Config

Ranking / fusion live under `dual_hybrid:` in `tkeir/configs/rag.yaml`
(block name is historical; runtime is
`PassageRetrievalPipeline`). Full reference:
[Configuration → rag.yaml](../configuration/rag.yaml.md).

Business ontology: `datasets/<name>/business_ontology.yaml` when
`business_ontology.index_enabled` / `search_enabled` are true.

## Rollback

1. Set `dual_hybrid.enabled: false` to use the legacy QueryAnalyzer
   single-arm path against the **`user`** schema (still no old
   `tkeir_document` / `chunk` schemas).
2. Keep a Vespa volume / application package backup before schema deploy
   if you need a binary rollback.

## Verification

- Document API paths use `global` / `user` (not `chunk` / `tkeir_document`).
- Hits expose `source_ref`, `chunk_text`, `ontology_concepts`, dense/sparse.
- `/search` uses `PassageRetrievalPipeline` when `dual_hybrid.enabled: true`;
  check `query_analysis` timings for Vespa arms.
