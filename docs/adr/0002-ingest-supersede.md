# ADR-0002: Ingest supersede and rollback strategy

## Status

Accepted (Phase 3 — placeholder hooks)

## Context

Ingest jobs are idempotent on `(doc_id, pipeline_config_sha256, embedder.sha256)`.
Operational teams need a documented path when content changes under the same
logical document name, or when a bad index must be rolled back.

## Decision

1. **Supersede:** When new bytes produce a different `doc_id`, the manifest
   `lineage.supersedes` field may reference the prior `ingest_id`. Vespa
   document ids remain content-addressed; supersede is metadata-only in Phase 3.
2. **Same bytes:** Identical content re-ingest is a **noop** (no pipeline/index).
3. **Config change:** A new `pipeline_config_sha256` or embedder fingerprint
   triggers a full re-run even for the same `doc_id`.
4. **Rollback:** Phase 3 exposes a **placeholder** — delete/reindex is manual
   via existing `tkeir-index-documents` and Vespa admin tools. Automated
   rollback hooks land with the governor/WORM audit workstream (Phase 4–5).

## Consequences

- Operators can trace lineage via manifests and correlation IDs.
- No automatic Vespa tombstone in Phase 3; document removal is out of scope here.
