# Generic / product-bundled reference ontologies

Place **application-neutral** OWL/TTL/RDF graphs here (shared across
deployments). Relative `derive-from.paths` in `document-ontology.yaml`
resolve against this directory via
`OntologyDerivation.default_search_roots()`.

Do **not** put corpus- or customer-specific ontologies here (for example
NATO C2SIM demo files under `workspace/corpus_nato/ontologies/`). Those
must be uploaded by the ingest **client** with each document
(`ontology_file` multipart or JSON `content_base64`); the server stages
them under `INGEST_ROOT` and never discovers them from the workspace.
