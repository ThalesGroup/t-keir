# Overview

TKEIR (Thales Knowledge Extraction To Information Retrieval) is an in-process document
analysis pipeline for knowledge extraction (tokenization, morphosyntax, named entity
recognition, dependency analysis, and keyword extraction), plus optional Vespa RAG
and an **agentic operations layer** (MCP tools, multi-agent workflows, ontology-driven
templates).

## Pipeline stages

1. **Converter** — raw text / PDF / Office → plain content (`MarkItDown`, optional OCR)
2. **Language detection** — select language-specific resources
3. **Tokenizer** — sentences, tokens, optional MWE compounds
4. **Morphosyntax** — POS tags and lemmas (spaCy)
5. **NER** — named entities with validation rules
6. **Syntax** — dependencies and Subject–Verb–Object triples
7. **Keywords** — RAKE-style extraction

Optional RAG path: chunking / questions → embed → Vespa streaming
(`tkeir_document` + `chunk`, group = Keycloak principal or `dev@tkeir`) →
hybrid retrieval → FastAPI RAG (`tkeir-rag`).

T-KEIR uses spaCy, NLTK, and Hugging Face models where configured.

## Agentic layer

Built **from scratch** on `UnifiedLLMWrapper` (no LangChain / CrewAI / etc.):

| Capability | Service / entry | Docs |
|---|---|---|
| MCP server (read-only corpus tools) | `tkeir-mcp` `:8093` | [MCP](tools/mcp.md) |
| Single- and multi-agent runtime | `tkeir-agent` `:8092` | [Agents](tools/agents.md) |
| Ontology → grounded templates | `make compose` / `thot.compose` | [Templates](tools/templates.md) |
| Run monitor + publish | HMI `/agents` | [HMI](hmi.md) |

Agents stay tenant-scoped (`user_space`), emit `ActionRecord`s, and obey the
governor (`agents` kill switch, budgets, ApprovalQueue). Publication of
generated content is approval-gated (`origin=agent-generated`).

## CLI tools (`thot/tools/` and agentic entry points)

| Component | Entry point | Module |
|---|---|---|
| Document pipeline | `tkeir-pipeline` | `thot.tools.pipeline` |
| Vespa indexing | `tkeir-index-documents` | `thot.tools.search.index_documents` |
| Vespa RAG API | `tkeir-rag` | `thot.tools.search.app` |
| Vespa bootstrap | `tkeir-init-vespa` | `thot.tools.search.init_vespa` |
| Annotation MWE trie | `tkeir-create-annotation-resource` | `thot.tools.annotation.create_annotation_resource` |
| MCP server | `tkeir-mcp` | `thot.mcp.server` |
| Agent / workflow service | `tkeir-agent` | `thot.agent.service` |
| Template compose CLI | `tkeir-compose` / `python -m thot.compose` | `thot.compose` |

The root `Makefile` invokes search modules as `python -m thot.tools.search.*`
and agentic targets (`make mcp`, `make agent`, `make workflow-run`,
`make compose`). Run `make help` from the repository root for all targets.
