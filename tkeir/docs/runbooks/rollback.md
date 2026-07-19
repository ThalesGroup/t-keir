# Index / action rollback runbook

## When

Bulk index/delete went wrong, or a governed rollback was requested.

## Steps

1. Identify the run / action id from the audit report or governor log.
2. Request rollback:
   ```bash
   make rollback-index RUN=<run_id> REASON="bad generation"
   ```
3. Confirm the governor recorded the request (`rollback-requests.jsonl` under
   `GOVERNOR_STATE_ROOT`).
4. Re-verify search quality and audit chain:
   ```bash
   make audit-verify
   make smoke-test
   ```

See ADR-0002 for supersede strategy.
