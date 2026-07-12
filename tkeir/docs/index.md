# Introduction

T-KEIR **2.0.0** is a document analysis toolkit that enriches JSON documents through a unified
in-process pipeline and optional Vespa-backed RAG.

## Features

- **Document conversion** — raw text, PDF, Office, HTML via MarkItDown
- **Tokenizer** — configurable multi-word expressions per language
- **Morphosyntax, NER, syntax** — spaCy-based tagging and knowledge-graph triples
- **Keywords** — RAKE extraction
- **Ontology export** — RDF graphs and HMI-friendly entity/keyword views
- **Vespa RAG** — 2-level document/chunk indexing and FastAPI query API

## Documentation

| Topic | Page |
|---|---|
| Quick start | [ready_to_run.md](ready_to_run.md) |
| Dev container | [devcontainer.md](devcontainer.md) |
| Pipeline tools | [tools/tools_overview.md](tools/tools_overview.md) |
| Vespa RAG | [tools/vespa_rag.md](tools/vespa_rag.md) |
| Python API examples | [tools/api_reference.md](tools/api_reference.md) |

## Source

[T-KEIR on GitHub](https://github.com/ThalesGroup/t-keir/)

## ChangeLog

| Date    | Description | Authors      |
| ------- | ----------- | ------------ |
| 2020/10 | 1.0.0       | Eric Blaudez |
| 2021/12 | 1.0.1       | Eric Blaudez |
| 2022/02 | 1.0.2       | Eric Blaudez |
| 2022/09 | 1.0.3       | Eric Blaudez |
| 2026/07 | 2.0.0       | Eric Blaudez |
