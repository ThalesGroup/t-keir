# DORA (Reg. 2022/2554) — engineering evidence mapping

> **Not legal advice.** ICT risk management, resilience testing, and third-party
> risk hooks, checked by `compliance/opa/policies/dora/dora.rego`
> (`package eu.dora`). Full audit: `make audit-compliance` —
> [EU Compliance OPA Audit](eu-audit.md).

## How the OPA policy decides

| `dora.in_scope` (`overrides.yaml`) | Behaviour |
|------------------------------------|-----------|
| `false` (default for generic demos) | **All** DORA articles → `NOT_MANDATORY` |
| `true` | Art.5–13, 17, 19, 24–26, 28, 30 evaluated |

Financial entities enabling DORA should set `in_scope: true` and complete the
attestation block under `dora.attestation`.

## Illustrative T-KEIR controls

| Article | Implementing feature | Evidence / command |
|---------|----------------------|--------------------|
| Art.6 / Art.8 | ICT framework + asset register | `make security-report`; `deploy/versions.lock.yaml` |
| Art.9 | Integrity / access control | ActionRecord hash chain; Keycloak → intents |
| Art.10 | Detection / alerting | Compose `observability` (Grafana/Prometheus) |
| Art.11 | BCP / backup / restore | `make rollback-index`; `make audit-verify` |
| Art.12 | Incident management | [incident runbook](../runbooks/incident.md) |
| Art.24 | Resilience testing | `make compose-smoke`; `make audit-verify` |
| Art.28 / Art.30 | ICT third-party risk | Lockfile + SBOM; contract attestations |
| Art.17 | Major ICT incident reporting | Attestations + `tkeir-audit incident` |

## Full OPA article catalogue

--8<-- "./docs/compliance/generated/dora_articles.md"

## Exact legal text (EUR-Lex)

Official English excerpts for each catalogue citation (paragraph / point when
available). Links in the table above jump here.

--8<-- "./docs/compliance/generated/dora_article_texts.md"

## Latest audit results

--8<-- "./docs/compliance/generated/dora_results.md"

## Related

- [EU Compliance OPA Audit](eu-audit.md)
- [Latest audit results](latest-results.md)
- 
- 
- [Governor](../deployment/governor.md)
