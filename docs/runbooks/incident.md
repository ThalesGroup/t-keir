# Incident response runbook

## Trigger

Audit write failure, WORM archiver failure, verify divergence, or security event.

## Immediate actions

1. Capture correlation IDs and timestamps (UTC).
2. Freeze risky scopes if needed:
   ```bash
   make governor-kill SCOPE=all ACTIVE=true REASON="incident"
   ```
3. Collect evidence:
   ```bash
   make audit-evidence
   make audit-verify
   ```
4. Draft early-warning / 72h notification templates (NIS2 hook):
   ```bash
   tkeir-audit incident --since 2026-01-01T00:00:00Z
   ```
   (CLI stub: use `make audit-report` / evidence pack until the incident
   subcommand is fully wired.)

## Restore

- Hot store: rebuild from WORM segments (`docs/deployment/audit.md`).
- Index: `make rollback-index RUN=<id>`.

> Engineering procedure — not legal advice.
