# Data subject request (forget) runbook

## Goal

Crypto-shred a subject's envelope key so hot-store / WORM segments remain
hash-valid while the subject becomes unreadable (GDPR erasure hook).

## Steps

1. Identify the subject id used at ingest / auth time (pseudonymized `sub`).
2. Run:
   ```bash
   tkeir-audit forget --subject <subject-id>
   ```
3. Confirm subsequent reports no longer resolve the subject.
4. Record the DSR as an ActionRecord / ops ticket (do not store raw PII).

See [GDPR mapping](../compliance/gdpr.md).
