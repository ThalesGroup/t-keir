# Ontology schema migration

Additive Vespa change: new chunk fields + `ontology_concept` document type.
Default hybrid ranking is unchanged. Re-index to populate new fields.

## What changed

| Item | Action |
|------|--------|
| `doc_base.ontology_concepts` | Kept (legacy name; values are concept IDs) |
| `doc_base.ontology_concept_ids` | Added (same values as `ontology_concepts` on write) |
| `doc_base.ontology_relations` | Added (`array<struct>`) |
| `doc_base.ontology_rel_keys` | Added (`subject\|predicate\|object`) |
| `ontology_concept` schema | New catalog document type in the `global` content cluster |
| Rank profile `hybrid_ontology` | Inherits `hybrid`; overlap weights are application-side |

Old indexes without the new fields remain queryable: YQL still ORs
`ontology_concepts contains "…"`.

## Procedure

1. Generate schemas: `make schemas` (already committed from `rag.yaml`).
2. Recreate / redeploy the Vespa app: `make clean-db && make bootstrap`
   (schema deploy on a dirty volume can fail; see
   [passage schema migration](dual-hybrid-migration.md)).
3. Re-index corpora (`make index`, ingest, or workspace index) so chunks
   receive `ontology_concept_ids` / relations and the concept catalog is
   upserted.
4. Smoke: text-only `POST /search` still returns hits; optional
   `concept_ids` / `POST /ontology/export`.

## Rollback

Redeploy the previous Vespa application package and keep serving against
`ontology_concepts` only. New API fields are optional; old clients are
unaffected.
