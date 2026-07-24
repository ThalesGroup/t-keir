# GDPR (Reg. 2016/679) — engineering evidence mapping

> **Not legal advice.** Privacy-by-design hooks for audit storage and DSR,
> checked by `compliance/opa/policies/gdpr/gdpr.rego` (`package eu.gdpr`).
> Full audit: `make audit-compliance` — [EU Compliance OPA Audit](eu-audit.md).

## How the OPA policy decides

GDPR checks are **always in scope** for the platform (processing of operational
and audit data is assumed). Many articles require **manual attestation** in
`overrides.yaml` → `gdpr.attestation.*` (`null` = not assessed). Repository
evidence covers minimisation, integrity, erasure, and security testing.

## Illustrative T-KEIR controls

| Article | Implementing feature | Evidence / command |
|---------|----------------------|--------------------|
| Art.5(1)(c) | Query text off by default (`request_hash`) | `tkeir/thot/action/schemas/action.v1.json` |
| Art.5(1)(e)/(f) | Retention + integrity | `AUDIT_WORM_RETENTION_DAYS`; WORM hash chain |
| Art.17 | Right to erasure — crypto-shredding | `tkeir-audit forget --subject <id>` (`thot/audit/privacy.py`) |
| Art.25 | Data protection by design/default | ActionRecord minimisation + privacy module |
| Art.32 | Security of processing | `make audit-verify`; `make security-report` |
| Art.35 | DPIA | `overrides.yaml` `gdpr.attestation.dpia` |
| Art.44–49 | International transfers | Flag OCR/`PROVIDER=openai` egress in DPIA |

## Caution

OCR `llm` mode and external LLM providers may send page content outside the
deployment boundary — call this out in DPIA templates for regulated deployments.

## Full OPA article catalogue

--8<-- "./docs/compliance/generated/gdpr_articles.md"

## Latest audit results

--8<-- "./docs/compliance/generated/gdpr_results.md"

## Reviewer checklist (legal vs automatic)

Items marked **Legal / reviewer (not code)** need human/legal sign-off in
`overrides.yaml`. Already-green engineering controls appear pre-checked.

--8<-- "./docs/compliance/generated/gdpr_reviewer_checklist.md"

## Related

- [EU Compliance OPA Audit](eu-audit.md)
- [Latest audit results](latest-results.md)
- [Legal / reviewer checklist](legal-review-checklist.md)
- [Security](../security.md)
- 
- [DSR runbook](../runbooks/dsr.md)
