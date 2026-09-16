# Ontology data model and retrieval

T-KEIR treats ontology as a **first-class semantic layer** beside dense, sparse,
and BM25 retrieval. Vespa stores and retrieves it; it is **not** the source of
truth for ontology semantics.

Canonical Python package: [`thot.ontology`](../../tkeir/thot/ontology/).

## Concepts vs chunk associations vs relations

| Layer | Meaning | Storage |
|-------|---------|---------|
| **Ontology concept** | First-class entity with a stable `concept_id` (label is only a property) | Vespa `ontology_concept` documents (corpus catalog, insert-if-absent) |
| **Ontology triple** | Corpus-level `(subject, predicate, object)` | Vespa `ontology_triple` (GET before PUT; never duplicated) |
| **Chunk → concept** | IDs of concepts associated with a passage | `ontology_concept_ids` (and legacy `ontology_concepts`) |
| **Chunk → document** | Indexed parent document this chunk was extracted from | `parent_doc_id` = `corpus_doc.document_id` |
| **Relation / assertion** | `(subject_id, predicate_id, object_id, confidence)` extracted from SVO / JSON / expert links | Chunk pointers `ontology_rel_keys`; graph in `ontology_triple` |

Do **not** duplicate the full concept graph on every chunk.

## Concept ID conventions

All IDs are minted in [`thot.ontology.identity`](../../tkeir/thot/ontology/identity.py).
Labels are never identifiers.

| Kind | Example |
|------|---------|
| Expert / business (preserved) | `C4ISR`, `technology:kubernetes` |
| Document-extracted | `doc:acme.corp` (minted when the surface form is not already a stable ID) |
| JSON attribute | `json:attribute:customer.country` |
| JSON value | `json:value:customer.country=france` |
| Predicate | `pred:has_value`, `pred:implements` |
| Legacy JSON (still written) | `DOMAIN:osint`, `CUSTOMER_COUNTRY:France` |

Existing business-ontology `concept_id` values are **kept as-is** so already
indexed chunks continue to match.

## Expert ontology and extension

```text
Expert / Business Ontology    (optional YAML seed, never overwritten)
        |
        v
Ontology extension
  - concepts extracted from documents (JSON-LD / SVO)
  - JSON structural attribute/value concepts
  - relations (SVO + has_value)
        |
        v
Extended ontology  →  Vespa ontology_concept  +  SHACL inductor
```

Provenance kinds: `expert_defined`, `document_extracted`, `json_extracted`,
`inferred`.

Indexing and search work with **no** expert ontology.

## Indexing flow

```text
source → parse → chunk → BGE-M3 dense/sparse
                      → OntologyService.enrich_chunk (union per document)
                      → corpus catalog GET/PUT ontology_concept + ontology_triple
                        (skip triples/concepts already stored in any corpus)
                      → Vespa global/user passage (parent_doc_id → corpus_doc)
                      → corpus_doc (BM25 + tags + author + simhash + concept pointers)
```

Search / RAG run the chunk hybrid arm, then a weighted ``corpus_doc`` arm
(`dual_hybrid.document_index.chunk_weight` / `document_weight`) and blend
scores by `parent_doc_id` before ColBERT.

Ontology enrichment is a dedicated stage in
`thot.tools.ingest.index_passages` (`OntologyService`). It does not change
generic chunking or embedding.

## Retrieval

Existing hybrid ranking is unchanged (`rank-profile hybrid`: dense 0.70 +
sparse 0.20 + BM25 0.10). Ontology is an **additional OR recall signal**.

```text
Query → semantic retrieval (NN + BM25 + sparse)
      → optional concept resolution / expansion (application-side)
      → YQL OR ontology_concept_ids / ontology_rel_keys
      → optional overlap rescore (concept / relation weights)
      → ColBERT
```

`POST /search` and `POST /rag/query` accept optional:

```json
{
  "query": "How is Kubernetes deployed?",
  "concept_ids": ["technology:kubernetes"],
  "relations": [{"predicate_id": "pred:implements", "object_id": "technology:cloud"}],
  "ontology_expand": {"include_children": true, "max_depth": 1}
}
```

Clients that send only `{"query": "..."}` are unchanged.

Relation match mode is configurable (`dual_hybrid.ontology_layer.relation_match`:
`exact` | `partial`).

Neighborhood expansion (parents / children / related / selected predicates)
runs **in the application** before Vespa, not inside every rank expression.

## Complete ontology export

`POST /ontology/export` reconstructs the concept graph for the indexed corpus:

1. Visit `ontology_concept` documents (paginated; no full chunk load).
2. Visit `ontology_triple` documents (corpus-level SPO, insert-if-absent).
3. If the catalog is empty (legacy index), Vespa **grouping** on
   `ontology_concepts` / `ontology_rel_keys`.

`POST /ontology/expand` walks the expert/catalog graph then you can retrieve
chunks with the expanded IDs.

## SHACL

[`thot.ontology.shacl`](../../tkeir/thot/ontology/shacl.py) converts the
canonical model to RDF and reuses the existing document-ontology inductor /
validator (`pyshacl`). No second ontology model.

## Ranking weights

Tune without code changes in `rag.yaml`:

```yaml
dual_hybrid:
  rank_profiles:
    passage:
      hybrid:            # Vespa first-phase (unchanged default)
        dense: 0.70
        sparse: 0.20
        bm25: 0.10
      hybrid_ontology:   # application overlap only (Vespa inherits hybrid)
        concept: 0.15
        relation: 0.10
  retrieval:
    ranking_profile: hybrid
```

Select Vespa profile `hybrid_ontology` via `ranking_profile` on the request
(inherits the same first-phase as `hybrid`). Concept/relation weights apply in
the application overlap rescorer so default text-only ranking does not change.

## Migration

Additive schema fields plus a new `ontology_concept` document type. Re-deploy
Vespa (`make bootstrap`) and re-index to populate the catalog and relation
fields. Old chunks remain searchable via `ontology_concepts`.

See [ontology schema migration](../runbooks/ontology-migration.md).
