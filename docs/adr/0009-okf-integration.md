# ADR-0009 — OKF (Open Knowledge Format) integration

- **Status:** Accepted
- **Date:** 2026-07-23
- **Deciders:** T-KEIR maintainers
- **Tags:** okf, export, wiki, agents, mcp

## Context

T-KEIR's enriched index (Vespa parent docs + ontology JSON-LD + SVO triples +
chunk citations) has no standard export surface for external agents and tools.
OKF v0.1 (Google Cloud, June 2026) defines an interoperable Markdown+frontmatter
bundle format consumable by any LLM agent without an SDK.

## Decision

1. New module `thot/okf/` — static and dynamic (query-scoped) OKF bundle exporter.
2. New MCP tools `okf_bundle_list` / `okf_bundle_get` — in-process, same pattern as search.
3. New agent `okf_curator` — grounded enrichment of OKF concepts from the corpus.
4. New workflow `okf_wiki_brief` — Query→Bundle→Curate→Compose, using a new builtin
   step type in the Orchestrator.
5. Compose profile `okf` + service `tkeir-okf` (:8095). Governor remains on
   :8094 so both can run together on the same host.
6. HMI `/okf` bundle browser.
7. T-KEIR producer extensions (`tkeir_*` frontmatter) remain in
   `tkeir_okf_version:"0.1"` namespace; OKF consumers ignore unknown keys per §9
   of the spec.
8. `user_space` isolation: bundle ownership is checked on every API route;
   `bundle_id` is scoped; `okf_bundle_get` enforces tenant match identically to
   `document_get`.
9. All exports emit ActionRecords (`ext.action_kind=okf.export.*`) under the
   governor `intent:okf.export` scope.
10. No third-party dependencies added (`rdflib`, `pysbd`, FastAPI already present).

## Consequences

- New CLI: `tkeir-okf-export`, `tkeir-okf`.
- Makefile: `okf`, `okf-export`, `okf-workflow`, `okf-bundle-ls`.
- `WorkflowStep` gains a `builtin` field; Orchestrator handles it and emits a
  `Handoff` so the blackboard remains the single source of truth.
- Output contract gains `okf_enrichment_v1` (enrichments recovered via
  `notes` JSON for applicator; `claim` + `chunk_ids` keep AgentLoop provenance).
- See [OKF](../tools/okf.md), [Agents](../tools/agents.md), [MCP](../tools/mcp.md).

## Related

- [ADR-0005](0005-agent-architecture.md) (agents)
- [ADR-0006](0006-kg-store.md) (KG)
- [ADR-0007](0007-generated-content.md) (publish)
