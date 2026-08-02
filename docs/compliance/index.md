# Compliance mappings

> Engineering evidence and requirement→feature→artifact→command tables.
> **Not legal advice.**

T-KEIR ships two complementary layers:

1. **Narrative mappings** (pages below) — human-readable requirement → control →
   command tables.
2. **OPA + OSCAL EU audit** ([eu-audit.md](eu-audit.md)) — machine-checkable
   policies under `compliance/opa/` that evaluate every wired article, emit
   `NOT_MANDATORY` when out of scope, and produce HTML **plus** OSCAL
   Assessment Results / POA&M under `reports/compliance/eu-audit/<version>/`.

After `make ci` (or `make audit-compliance`), the **full** article outcomes are
also published into MkDocs — see [Compliance status (one page)](status.md) and
[Latest audit results](latest-results.md).

For the catalogue of **all** CI reports and GitHub Actions (not only OPA
evidence), see [CI, reports & Actions](../ci/index.md).

```bash
make audit-compliance   # OPA audit → reports/… + docs/compliance/generated/
make audit-evidence     # reports/evidence/<version>/
make annex-iv           # reports/compliance/annex-iv/
```

## Regulation pages

| Doc | Regulation | OPA package |
|-----|------------|-------------|
| [EU Compliance OPA Audit](eu-audit.md) | Tool, result model, category gates | all |
| [Compliance status (one page)](status.md) | Colored status · criticality · remediation | all |
| [Latest audit results](latest-results.md) | Last CI / audit snapshot (full outcomes) | all |
| [Legal / reviewer checklist](legal-review-checklist.md) | GDPR/CRA human vs automatic checkboxes | `eu.gdpr` / `eu.cra` |
| [ai-act.md](ai-act.md) | AI Act Reg. (EU) 2024/1689 | `eu.ai_act` |
| [cra.md](cra.md) | CRA Reg. (EU) 2024/2847 | `eu.cra` |
| [nis2.md](nis2.md) | NIS2 Dir. (EU) 2022/2555 | `eu.nis2` |
| [dora.md](dora.md) | DORA Reg. (EU) 2022/2554 | `eu.dora` |
| [gdpr.md](gdpr.md) | GDPR Reg. (EU) 2016/679 | `eu.gdpr` |
| [pld.md](pld.md) | PLD Dir. (EU) 2024/2853 | `eu.pld` |
| [ci-evidence.md](ci-evidence.md) | CI / SBOM / security artefacts | feeds `input.evidence` |

Also see [Identity of Action](../regularity-component/action-identiy.md),
[Mastering of Action](../regularity-component/action-mastering.md), and [Security](../security.md).
