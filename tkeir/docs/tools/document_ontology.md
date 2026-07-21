# Document ontology

Pipeline task that builds an RDF document graph from analyzed T-KEIR content
(KG / NER / keywords), validates it with SHACL, and stores JSON-LD on the
document for Vespa (`json_ld` field).

Config: `tkeir/configs/document-ontology.yaml`.

## Derive from an existing ontology

Before SHACL / Vespa serialization, the builder can **enrich** the document
graph from one or more reference ontologies (OWL/TTL/RDF), for example the
C2SIM / C4ISR files produced by `make corpus`:

```text
workspace/corpus_nato/ontologies/c2sim_combined.ttl
workspace/corpus_nato/ontologies/c2sim_c4isr.ttl
```

Enable in config:

```yaml
document-ontology:
  builders:
    - derive-from:
        enabled: true
        paths:
          - workspace/corpus_nato/ontologies/c2sim_combined.ttl
        similarity-threshold: 0.8
        match-classes: true
        match-individuals: true
        add-subclass-links: true
        add-type-links: true
        add-same-as-links: true
        include-matched-axioms: false   # copy matched reference triples
      save-derivation: true             # full match details in document_ontology
```

Or per document (overrides / extends paths):

```json
{
  "derive_from_ontologies": ["workspace/corpus_nato/ontologies/c2sim_c4isr.ttl"]
}
```

Matching is label-based (exact, containment, lemma Jaccard). Links added:

| Match | Triple |
|-------|--------|
| Document class ↔ reference class | `rdfs:subClassOf` |
| Document individual ↔ reference class | extra `rdf:type` |
| Document individual ↔ reference individual | `owl:sameAs` |

Implementation: `thot.tasks.document_ontology.OntologyDerivation`.
