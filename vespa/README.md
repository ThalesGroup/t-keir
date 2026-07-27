# Vespa RAG stack

This directory contains the Vespa Docker deployment (schemas, shell scripts).
Python **indexing** lives in `tkeir/thot/tools/ingest/`; **search / RAG** in
`tkeir/thot/tools/search/`; **BEIR eval** in `tkeir/thot/tools/eval/`.
All Make targets live in the **repository root** `Makefile` — run them from the repo root.

- **`doc_base`** — shared fields (`source_ref`, `chunk_text`, sparse, `ontology_concepts`)
- **`global`** — index-mode catalog; `dense_vector` with HNSW
- **`user`** — streaming-mode tenant passages (`userspace_id` + attribute-only `dense_vector`)

Schemas are generated from `tkeir/configs/rag.yaml` (`make schemas`).
BGE-M3 weights for FlagEmbedding: `tkeir/resources/modeling/net/bge-m3`
(`make pull-bge-model`).

## Quick start

```bash
# From repository root
make install
make bootstrap

export PROVIDER=ollama
export EMBEDDING_MODEL=BAAI/bge-m3
make index-fixtures
make index

make rag
make rag-query RAG_QUERY="Who is Rob Brown?"
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
