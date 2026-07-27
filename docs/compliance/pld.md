# Product Liability Directive (Dir. 2024/2853) — engineering evidence mapping

> **Not legal advice.** Defect-evidence and disclosure hooks binding outputs to
> exact versions, checked by `compliance/opa/policies/pld/pld.rego`
> (`package eu.pld`). Full audit: `make audit-compliance` —
> [EU Compliance OPA Audit](eu-audit.md).

## How the OPA policy decides

| `pld.in_scope` (`overrides.yaml`) | Behaviour |
|-----------------------------------|-----------|
| `false` | **All** PLD articles → `NOT_MANDATORY` |
| `true` (default) | Art.4–18, 22 evaluated |

## Illustrative T-KEIR controls

| Article | Implementing feature | Evidence / command |
|---------|----------------------|--------------------|
| Art.4 | Software / AI product | `product.is_software` in overrides |
| Art.5 / Art.12 | Proof chain & disclosure | `make audit-report CID=…` |
| Art.6 | Defectiveness criteria | `make bom`; `make trivy` |
| Art.9 / Art.14 | Evidence preservation | WORM retention; `make audit-verify` |
| Art.11 / Art.17 | Time limits / long-stop | `CHANGELOG.md`; version history in lockfile |
| Art.15 | Burden of proof support | `make audit-evidence` |

## Full OPA article catalogue

--8<-- "./docs/compliance/generated/pld_articles.md"

## Exact legal text (EUR-Lex)

Official English excerpts for each catalogue citation. Links in the table above
jump here.

--8<-- "./docs/compliance/generated/pld_article_texts.md"

## Latest audit results

--8<-- "./docs/compliance/generated/pld_results.md"

## Related

- [EU Compliance OPA Audit](eu-audit.md)
- [Latest audit results](latest-results.md)
- [CI and evidence pipeline](ci-evidence.md)
- [CRA mapping](cra.md)
