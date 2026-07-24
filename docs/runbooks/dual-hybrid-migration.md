# Dual-hybrid schema migration (parent_* removal)

Removing `parent_title` / `parent_content` from `chunk.sd` is a **breaking**
Vespa schema change. Streaming corpora must be fully reindexed.

## Prerequisites

1. Regenerate schemas from config:

   ```bash
   make schemas
   make schemas-check
   ```

2. Deploy schemas (`make init` or Compose bootstrap).

3. Lemmatized fields use `stemming: none` / `normalizing: none` and live in
   fieldset `lemmatized` (not `default`) so Vespa does not warn about
   inconsistent linguistics vs raw `title`/`content`. If Vespa rejects those
   attributes, remove them from the Jinja templates, regenerate, and redeploy.
   Document the fallback in the templates' comments (default Vespa linguistics
   then apply on already-normalized text).

## Reindex order

1. **Documents first** (`tkeir_document`) so the document arm and
   `json_ld` are populated before dual-hybrid fusion relies on them.
2. **Chunks second** (`chunk`) without parent denormalization; each chunk
   must carry `doc_ref` and `source_doc_id`.

Typical host path:

```bash
make init
make index   # indexes documents then chunks per pipeline JSON
```

For Compose / cluster, rebuild images that bake schemas, redeploy the
Vespa app package, then re-run the indexer job against the ingest store.

## Config knobs

All ranking weights live under `dual_hybrid:` in `tkeir/configs/rag.yaml`.
Business ontology concepts are passed **per query** via
`business_ontology` on `/search` and `/rag/query` (not loaded from disk).
Zero-to-Hero payloads: `datasets/osint/business_ontology.yaml` and
`datasets/enterprise/business_ontology.yaml`.
SpaCy models are selected by request/document language from
`preprocessing.spacy_models` (mandatory `default` entry).
Asciifold after lemmatization is controlled by `preprocessing.asciifold`
(default `true`).

Estimate real `averageFieldLength` values:

```bash
python scripts/measure_field_lengths.py -i workspace/tmp/pipeline-out
make schemas
```

## Rollback

1. Set `dual_hybrid.enabled: false` in `rag.yaml` to restore the legacy
   QueryAnalyzer single-arm path (still without parent BM25 unless you
   restore the old schema).
2. To restore parent denormalization, check out the previous `chunk.sd`,
   redeploy, and reindex chunks with the old `_chunk_fields` mapping.
3. Keep a backup of the prior Vespa application package / volume snapshot
   before schema deploy if you need a fast binary rollback.

## Verification

- Chunk hits no longer expose `parent_title` / `parent_content`.
- Document hits include `title_lemmatized` / `content_lemmatized`.
- `/search` response `query_analysis.dual_hybrid` lists active / degraded
  signals and per-stage timings when dual hybrid is enabled.
