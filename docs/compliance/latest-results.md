# Latest EU compliance audit results

> **Not legal advice.** Snapshot of the most recent OPA evaluation published into
> the docs by `make audit-compliance` / `make ci` (via
> `compliance/opa/scripts/gen_doc_results.py`).

Source of truth for the machine artefacts remains under
`reports/compliance/eu-audit/<version>/` (gitignored). This page embeds the
**full** article outcomes (violations, passed, and `NOT_MANDATORY`) so MkDocs
always reflects the last CI / audit run.

See [EU Compliance OPA Audit](eu-audit.md) for the result model and how to
re-run the audit. For a single colored table (status · criticality ·
remediation) see [Compliance status](status.md). For GDPR/CRA items that only
a human can close, see the [Legal / reviewer checklist](legal-review-checklist.md).

--8<-- "./docs/compliance/generated/latest_results.md"
