# ADR-0003: Two-tier audit store (hot PostgreSQL + WORM)

## Status

Accepted (Phase 4)

## Context

T-KEIR must produce hash-chained ActionRecords queryable in **< 5 s p95**
while retaining immutable compliance archives (NIS2/DORA record-keeping).

Alternatives considered: immudb-only, Loki + object-lock, Postgres-only without
WORM.

## Decision

1. **Hot tier**: PostgreSQL (compose/Helm) or SQLite (local tests) append-only
   `action_records` table with hash chain; `archive_refs` tracks WORM exports
   without mutating record payloads.
2. **WORM tier**: gzip JSONL segments + SHA-256 sidecars under
   `AUDIT_WORM_ROOT` (filesystem in dev; S3/MinIO object-lock in production).
3. **Archiver**: hourly CronJob (`tkeir-audit archive`) closes batches and
   writes daily chain-head anchors.
4. **Verification**: `tkeir-audit verify` re-hashes hot chain and validates
   WORM segment digests.
5. **GDPR**: envelope keys in a separate SQLite store; `forget` crypto-shreds
   subjects without breaking hash chains.

## Consequences

- Services mirror ActionRecords via `AUDIT_SINK_MODE=dual` when
  `AUDIT_HOT_STORE_URL` is set.
- Production installs enable MinIO/S3 object-lock at bucket creation; compose
  uses filesystem WORM for developer parity.
- Governor enforcement and signed anchors land in Phases 5–9.
