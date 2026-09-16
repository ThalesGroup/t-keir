# Ontology schema migration

Additive Vespa change: corpus-level `ontology_triple`, document-level
`corpus_doc`, and chunk `parent_doc_id` / `chunk_id`.
Default hybrid ranking is unchanged. Re-index to populate new fields.

## What changed

| Item | Action |
|------|--------|
| `doc_base.ontology_concepts` | Kept (legacy name; values are concept IDs) |
| `doc_base.ontology_concept_ids` | Added (same values as `ontology_concepts` on write) |
| `doc_base.ontology_relations` | Added (`array<struct>`) |
| `doc_base.ontology_rel_keys` | Added (`subject\|predicate\|object`) |
| `doc_base.parent_doc_id` | Indexed `corpus_doc` key this chunk was extracted from |
| `doc_base.chunk_id` | Logical golden-chunk id |
| `ontology_concept` schema | Concept catalog in the `global` content cluster (insert-if-absent) |
| `ontology_triple` schema | Corpus-level SPO catalog (GET then insert; skip existing triples) |
| `corpus_doc` schema | Document-level BM25 + tags + author + simhash + ontology pointers |
| Rank profile `hybrid_ontology` | Inherits `hybrid`; overlap weights are application-side |
| Search / RAG | Weighted blend of chunk arm + `corpus_doc` arm |

Old indexes without the new fields remain queryable: YQL still ORs
`ontology_concepts contains "…"`.

## Procedure

1. Generate schemas: `make schemas` (already committed from `rag.yaml`).
2. Recreate / redeploy the Vespa app: `make clean-db && make bootstrap`
   (schema deploy on a dirty volume can fail; see
   [passage schema migration](dual-hybrid-migration.md)).
3. Re-index corpora (`make index`, ingest, or workspace index) so chunks
   receive `parent_doc_id` / `ontology_concept_ids`, the concept/triple
   catalog is insert-if-absent, and `corpus_doc` rows are written.
4. Smoke: text-only `POST /search` still returns hits; optional
   `concept_ids` / `POST /ontology/export`. Document-arm blend logs
   `vespa_document` in dual-hybrid timings.

## Rollback

Redeploy the previous Vespa application package and keep serving against
`ontology_concepts` only. New API fields are optional; old clients are
unaffected.
