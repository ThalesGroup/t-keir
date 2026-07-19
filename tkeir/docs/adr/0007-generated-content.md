# ADR-0007 — Agent-generated content publication

- **Status:** Accepted (Phase E)
- **Date:** 2026-07-19
- **Deciders:** T-KEIR maintainers
- **Tags:** agents, ingest, provenance, approvals

## Context

Agents produce grounded markdown/JSON deliverables. Publishing them into the
corpus must not bypass governor approvals, must carry provenance, and must
reuse supersede/rollback (ADR-0002) for retraction.

## Decision

1. Publication is **approval-gated**: `POST /agent/runs/{id}/publish` requires
   an approved ApprovalQueue item in `GOVERNOR_MODE=enforce` (intent
   `generate` / reason includes `run_id=`).
2. Staged packages live under `AGENT_ROOT/publishes/{run_id}/` with
   `document.md` + `publish.manifest.json`.
3. Ingest manifests may carry optional `origin: agent-generated` and `run_id`
   (schema `ingest.manifest.v1`).
4. Agent retrieval **excludes** `origin=agent-generated` by default; set
   `AGENT_INCLUDE_GENERATED=1` to include (indexer/query filter — document the
   Vespa field when persisted).
5. Retraction uses the existing supersede/rollback path (ADR-0002) plus the
   [retract generated content](../runbooks/retract-generated.md) runbook.

## Consequences

- HMI `/agents` exposes Publish; `/admin` approves.
- No autonomous write/delete on the corpus from the agent loop.
- See [Agents](../tools/agents.md) and [Ingest](../deployment/ingest.md).
