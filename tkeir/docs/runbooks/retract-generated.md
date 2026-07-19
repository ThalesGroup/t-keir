# Runbook — Retract agent-generated content

Remove or supersede a published agent deliverable (`origin=agent-generated`).

## Identify

- Publish manifest: `AGENT_ROOT/publishes/{run_id}/publish.manifest.json`
- Ingest job / Vespa parent carrying `run_id` / `origin`
- Correlation id from the agent run

## Retract

1. Deny further publishes for the run (ApprovalQueue deny if pending).
2. Prefer **supersede** with a corrected document or empty tombstone via the
   ingest supersede path (ADR-0002):

```bash
# Example — re-ingest a replacement that supersedes the prior doc_id
# (exact flags depend on your ingest client / operator runbook)
curl -X POST http://localhost:8091/ingest/document \
  -H 'content-type: application/json' \
  -d '{"url":"file:///path/to/replacement.md","filename":"retraction.md"}'
```

3. If Vespa delete is authorized, use the governed delete intent (never from
   the agent loop itself).
4. Record the retraction ActionRecord / audit note with the original
   `correlation_id` and `run_id`.

## Verify

- Search no longer returns the retracted parent (or returns the superseding
  version).
- Agent retrieval still excludes `agent-generated` unless
  `AGENT_INCLUDE_GENERATED=1`.

## Related

- ADR-0002, ADR-0007
- [Ingest deployment](../deployment/ingest.md)
- [Kill switch](kill-switch.md)
