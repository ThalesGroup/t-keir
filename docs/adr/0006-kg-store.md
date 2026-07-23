# ADR-0006 — Per-tenant fused KG store

- **Status:** Accepted (Phase C)
- **Date:** 2026-07-19
- **Deciders:** T-KEIR maintainers
- **Tags:** ontology, kg, sparql, vespa

## Context

Document analysis already produces per-document RDF (Turtle / JSON-LD) stored
on Vespa parent documents. Agents and templates need a fused view per
`user_space` with SPARQL, without introducing a separate vector store or
rewriting Vespa schemas.

## Decision

1. Fuse parent ontologies in-process with
   `thot.tools.search.ontology_utils.merge_turtle_graphs`.
2. Expose the fused graph via `thot.compose.kg.UserSpaceKG` with an isolated
   SPARQL backend (`RdflibSparqlBackend`) so oxigraph (or another store) can
   replace rdflib later.
3. Cache per `user_space` in-process; invalidate on supersede / explicit
   `invalidate()`.
4. Do **not** add a new durable KG database in Phase C–E.

## Consequences

- Template composition and `ontology_query` share the same merge utilities.
- Process restarts rebuild the cache from Vespa / Turtle fixtures.
- See [Templates](../tools/templates.md) and ADR-0002 (supersede).
