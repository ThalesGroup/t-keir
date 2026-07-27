# CRA (Reg. 2024/2847) — engineering evidence mapping

> **Not legal advice.** Cyber Resilience Act alignment via supply-chain and
> secure-by-default controls, checked by `compliance/opa/policies/cra/cra.rego`
> (`package eu.cra`). Full audit: `make audit-compliance` —
> [EU Compliance OPA Audit](eu-audit.md).

## How the OPA policy decides

- **Annex I Part I** (essential cybersecurity requirements) — always evaluated
  against the **product** (T-KEIR software).
- **Annex I Part II** (vulnerability handling) — manufacturer context
  (SBOM, CVD, update signing).
- **Art.6** — product class (`overrides.yaml` → `product.cra_class`).
- **Art.13–14** — manufacturer obligations and ENISA reporting attestations.
- **Art.20–22** — authorised representative / importer / distributor:
  `NOT_MANDATORY` unless `product.role` matches.

## Illustrative T-KEIR controls

| Clause / article | Implementing feature | Evidence / command |
|------------------|----------------------|--------------------|
| Annex I §1(a) | No known exploitable vulns at release gate | `make trivy`; `make pip-audit` |
| Annex I §1(b) | Secure-by-default Helm presets | `deploy/charts/tkeir/values-secure.yaml` |
| Annex I §1(c)/(r) | AuthN/Z | Keycloak `realm-tkeir.json`; governor intents |
| Annex I Part II §1 | SBOM | `make bom` → `reports/bom/` |
| Annex I Part II §4 | CVD | `SECURITY.md` |
| Art.13(10)–(11) | Support period + security contact | `CHANGELOG.md`; `SECURITY.md` |
| Art.13(2)/versions | Third-party diligence | `deploy/versions.lock.yaml` |

## Full OPA article catalogue

--8<-- "./docs/compliance/generated/cra_articles.md"

## Exact legal text (EUR-Lex)

Official English excerpts for each catalogue citation (including Annex I
essential requirements). Links in the table above jump here.

--8<-- "./docs/compliance/generated/cra_article_texts.md"

## Latest audit results

--8<-- "./docs/compliance/generated/cra_results.md"

## Reviewer checklist (legal vs automatic)

Items marked **Legal / reviewer (not code)** (CE marking, ENISA reporting SLAs,
encryption attestations, …) need manufacturer/legal confirmation. Engineering
controls that already pass OPA are pre-checked.

--8<-- "./docs/compliance/generated/cra_reviewer_checklist.md"

## Related

- [EU Compliance OPA Audit](eu-audit.md)
- [Latest audit results](latest-results.md)
- [Legal / reviewer checklist](legal-review-checklist.md)
- [Security](../security.md)
- [CI and evidence pipeline](ci-evidence.md)
