# Runbook — Prompt injection incident

Malicious instructions appeared in retrieved chunks or external MCP tool
outputs and may have influenced an agent.

## Immediate actions

1. Kill scope **`agents`** if runs are still active.
2. Capture evidence: run id, correlation id, step JSON, tool observation
   `_untrusted_view`, and the offending chunk/document ids.
3. Deny any pending publish approvals for the run in `/admin`.
4. If content was already published, follow
   [Retract generated content](retract-generated.md).

## Verify defenses

- Tool allow-list rejected out-of-policy tools (`delete`, `ingest`, …).
- Untrusted envelopes present in step history (`<untrusted source=…>`).
- `detect_injection` / safety unit tests still pass in CI.

## Hardening follow-ups

- Tighten egress allow-list (`configs/mcp-client.yaml`).
- Reduce agent `tools:` allow-list for the affected workflow.
- Consider temporary `GOVERNOR_MODE=enforce` if not already.

## Related

- [Agents](../tools/agents.md) — safety envelopes
