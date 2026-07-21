# EU AI Act (Reg. 2024/1689) — engineering evidence mapping

> **Not legal advice.** This page maps AI Act articles to T-KEIR controls and to
> the OPA policy `compliance/opa/policies/ai_act/ai_act.rego` (`package eu.ai_act`).
> Run the full machine check with `make audit-compliance` — see
> [EU Compliance OPA Audit](eu-audit.md).

## How the OPA policy decides

1. Read `input.ai_act.classification.determined_category`
   (`UNACCEPTABLE` · `HIGH_RISK` · `LIMITED_RISK` · `MINIMAL_RISK` ·
   `GPAI_STANDARD` · `GPAI_SYSTEMIC`).
2. Evaluate **Art.5** for every category (prohibited-practice flags).
3. For each catalogue article, apply its **applicability gate**; if the gate
   fails → emit `NOT_MANDATORY` (not a violation).
4. If the gate passes, require the listed `evidence.*` and/or `attestation.*`
   fields to be **explicitly `true`**.

Source of truth for category computation:
`compliance/opa/collectors/input_generator.py` → `determine_ai_act_category()`.
Overrides: `compliance/opa/overrides.yaml` → `ai_act.classification`.

## Illustrative T-KEIR controls (high-signal)

| Article | Implementing feature | Evidence / command |
|---------|----------------------|--------------------|
| Art.5 | Product design + attestation of no prohibited practices | `overrides.yaml` `prohibited_practices.*` |
| Art.11 / Annex IV | Technical documentation pack | `make annex-iv` → `reports/compliance/annex-iv/` |
| Art.12 | ActionRecords + hot store + WORM | `action.v1.json`; `make audit-report`; `make audit-verify` |
| Art.14 | Governor kill switch, approvals, HMI `/admin` | `make governor-kill`; [kill-switch runbook](../runbooks/kill-switch.md) |
| Art.15 | BEIR evaluation; security scans | `make beir-eval`; `make trivy` |
| Art.50 | Transparency when LIMITED/HIGH risk | `overrides.yaml` `transparency.*` |
| Art.53–55 | GPAI documentation / systemic duties | AIBOM + attestations when `is_gpai_model` |

## Full OPA article catalogue

Tables below are generated from the Rego catalogue
(`python3 compliance/opa/scripts/gen_doc_tables.py`). Each row is one OPA check
id; the gate column states when the article is mandatory vs `NOT_MANDATORY`.

--8<-- "./docs/compliance/generated/ai_act_articles.md"

## Latest audit results

Full outcomes from the last `make audit-compliance` / `make ci` run (also on
[Latest audit results](latest-results.md)):

--8<-- "./docs/compliance/generated/ai_act_results.md"

## Related

- [EU Compliance OPA Audit](eu-audit.md)
- [Latest audit results](latest-results.md)
- [Identity of Action](../regularity-component/action-identiy.md)
- [Mastering of Action](../regularity-component/action-mastering.md)
- [CI and evidence pipeline](ci-evidence.md)
- ADR-0003 (audit + WORM), ADR-0008 (agent SPIFFE / SPIRE)
