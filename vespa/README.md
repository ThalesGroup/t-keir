# Vespa RAG stack

This directory contains the Vespa Docker deployment (schemas, shell scripts).
Python **indexing** lives in `tkeir/thot/tools/ingest/`; **search / RAG** in
`tkeir/thot/tools/search/`; **BEIR eval** in `tkeir/thot/tools/eval/`.
All Make targets live in the **repository root** `Makefile` — run them from the repo root.

- **`doc_base`** — shared fields (`source_ref`, `parent_doc_id`, `chunk_id`, `chunk_text`, sparse, ontology pointers)
- **`global`** — index-mode catalog; `dense_vector` with HNSW
- **`user`** — streaming-mode tenant passages (`userspace_id` + attribute-only `dense_vector`)
- **`ontology_concept`** — concept catalog (labels, aliases, graph links, optional embedding)
- **`ontology_triple`** — corpus-level SPO (insert-if-absent across all corpora)
- **`corpus_doc`** — document-level BM25 + tags + author + simhash + ontology pointers

`vespa/snapshot_index.sh` tars `/opt/vespa/var` for `INDEX_SNAPSHOT=1 ./start_services.sh`
(or `make save-index` / `make restore-index`).

Schemas are generated from `tkeir/configs/rag.yaml` (`make schemas`).
BGE-M3 weights for FlagEmbedding: `tkeir/resources/modeling/net/bge-m3`
(`make pull-bge-model`).

## Quick start

```bash
# From the repo root
make clean-db
make bootstrap
make vespa-check
make test-vespa    # counts for global / ontology_concept / user (all 0)

# Index only when you choose to (not part of bootstrap):
# make ingest   # then POST /ingest/json-records or HMI

# Optional: tar / restore the data volume (same archive as INDEX_SNAPSHOT=1)
# make save-index
# make restore-index
```

## Health checks

```bash
./vespa/check_vespa.sh
./vespa/test_data.sh
```

## CLI

| Command | Module |
|---|---|
| `tkeir-init-vespa` | `thot.tools.search.init_vespa` |
| `tkeir-index-documents` | `thot.tools.ingest.index_documents` |
| `tkeir-rag` | `thot.tools.search.app` |
