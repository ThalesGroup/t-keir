# Generic / product-bundled reference ontologies

Place **application-neutral** OWL/TTL/RDF graphs here (shared across
deployments). Relative `derive-from.paths` in `document-ontology.yaml`
resolve against this directory via
`OntologyDerivation.default_search_roots()`.

Do **not** put Zero-to-Hero or customer-specific ontologies here.
OSINT C2SIM graphs and business ontologies live under versioned
`datasets/osint/` and `datasets/enterprise/` (see [Datasets](../../../docs/tools/datasets.md)).
Those must be uploaded by the ingest **client** with each document
(`ontology_file` multipart or JSON `content_base64`); the server stages
them under `INGEST_ROOT` and never discovers them from the workspace.

Business ontologies for passage-retrieval query expansion are request payloads
(`business_ontology` on `/search` / `/rag/query`), sourced from
`datasets/{osint,enterprise}/business_ontology.yaml`.
