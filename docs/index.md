# Introduction

T-KEIR **2.0.0** is a document analysis toolkit that enriches JSON documents through a unified
in-process pipeline and optional Vespa-backed RAG, with an **agentic layer** for
tool-using research, ontology-driven document composition, and governed publication.

## Features

- **Document conversion** — universal extract (PDF, Office, HTML, images, ZIP, JSON, markdown) plus MarkItDown; multilingual Tesseract OCR and optional BLIP captions
- **Tokenizer** — configurable multi-word expressions; European spaCy pipelines and Arabic `blank:ar`
- **Morphosyntax, NER, syntax** — spaCy-based tagging and knowledge-graph triples
- **Keywords** — RAKE extraction
- **Corpus JSON** — `tkeir-corpus` builds `{dataset, records}` for `POST /ingest/json-records` from markdown or a mixed-format source tree
- **Ontology export** — RDF graphs and HMI-friendly entity/keyword views
- **Vespa RAG** — passage schemas (`global` index + `user` streaming),
  per-user spaces (Keycloak / `dev@tkeir`), and FastAPI query API
- **MCP server** — read-only corpus tools (`search`, `rag_query`,
  `ontology_query`, `document_get`) for external MCP clients
- **Agents & workflows** — from-scratch single- and multi-agent runtime
  (`tkeir-agent`), YAML-configured roles, governor kill switch / budgets /
  approvals, outbound MCP client with egress allow-list
- **Ontology-driven templates** — grounded document composition
  (`synthesis_note`, `entity_profile`) with cited slots and unfilled reporting
- **HMI** — RAG dashboard, agent run monitor (`/agents`), admin oversight

## Documentation

| Topic | Page |
|---|---|
| **Zero to Hero (dev → prod)** | [zero_to_hero.md](zero_to_hero.md) |
| NLP (pipeline quickstart) | [ready_to_run.md](ready_to_run.md) |
| Installation | [installation.md](installation.md) |
| Dev container | [devcontainer.md](devcontainer.md) |
| **Configuration (all YAML, field effects)** | [configuration/index.md](configuration/index.md) |
| Deployment profiles | [deployment/index.md](deployment/index.md) |
| Pipeline tools | [tools/tools_overview.md](tools/tools_overview.md) |
| Corpus (markdown or mixed files → ingest JSON) | [tools/corpus.md](tools/corpus.md) |
| Converter | [tools/converter.md](tools/converter.md) |
| Vespa RAG | [tools/vespa_rag.md](tools/vespa_rag.md) |
| MCP server | [tools/mcp.md](tools/mcp.md) |
| Agents & workflows | [tools/agents.md](tools/agents.md) |
| Templates (compose) | [tools/templates.md](tools/templates.md) |
| HMI | [hmi.md](hmi.md) |
| Python API examples | [tools/api_reference.md](tools/api_reference.md) |
| **CI, reports & Actions** | [ci/index.md](ci/index.md) |
| EU compliance (OPA, Rego, OSCAL) | [OPA, Rego, and OSCAL](compliance/opa-rego-oscal.md) · [audit](compliance/eu-audit.md) |
| Quality dashboard | [quality/index.md](quality/index.md) |

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
