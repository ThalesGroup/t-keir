# NIS2 (Dir. 2022/2555) — engineering evidence mapping

> **Not legal advice.** Cybersecurity risk-management and incident reporting
> hooks, checked by `compliance/opa/policies/nis2/nis2.rego` (`package eu.nis2`).
> Full audit: `make audit-compliance` — [EU Compliance OPA Audit](eu-audit.md).

## How the OPA policy decides

Set `nis2.entity_type` in `compliance/opa/overrides.yaml`:

| Value | Behaviour |
|-------|-----------|
| `OUT_OF_SCOPE` | **All** NIS2 articles → `NOT_MANDATORY` |
| `IMPORTANT` / `ESSENTIAL` | Art.20–27 evaluated against evidence + attestations |

## Illustrative T-KEIR controls

| Article | Implementing feature | Evidence / command |
|---------|----------------------|--------------------|
| Art.21(2)(a) | Secure deployment presets | `values-secure.yaml` |
| Art.21(2)(b) | Incident handling | [incident runbook](../runbooks/incident.md); `tkeir-audit incident` |
| Art.21(2)(c) | Continuity / restore | `make rollback-index`; `make audit-verify` |
| Art.21(2)(d) | Supply chain | `deploy/versions.lock.yaml`; `make bom` |
| Art.21(2)(i)/(j) | Access control / MFA | Keycloak realm; Compose `auth` profile |
| Art.21(4) | Network segmentation | `deploy/charts/tkeir/templates/networkpolicy.yaml` |
| Art.23 | Reporting timelines | Early-warning / incident CLI + attestations |

## Full OPA article catalogue

--8<-- "./docs/compliance/generated/nis2_articles.md"

## Exact legal text (EUR-Lex)

Official English excerpts for each catalogue citation. Links in the table above
jump here.

--8<-- "./docs/compliance/generated/nis2_article_texts.md"

## Latest audit results

--8<-- "./docs/compliance/generated/nis2_results.md"

## Related

- [EU Compliance OPA Audit](eu-audit.md)
- [Latest audit results](latest-results.md)
- [Secure cluster (P3)](../deployment/k8s-secure.md)
- [Kill-switch runbook](../runbooks/kill-switch.md)
