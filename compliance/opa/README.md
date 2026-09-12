# EU Compliance OPA Audit Tool

Machine-checkable mappings from T-KEIR repository evidence to EU regulations
(AI Act, CRA, GDPR, NIS2, DORA, PLD). **Not legal advice.**

Three layers (read this first if the acronyms are new):

| Layer | Role |
|-------|------|
| **OPA** | Policy engine (`opa eval`) that scores the generated evidence JSON |
| **Rego** | Policy language under `policies/` (`package eu.ai_act`, …) |
| **OSCAL** | NIST JSON documents for catalogs / SSP / assessment results / POA&M |

Canonical primer: [OPA, Rego, and OSCAL](../../docs/compliance/opa-rego-oscal.md).

## Quick start

```bash
# From repository root
make audit-compliance
```

Requires [OPA](https://www.openpolicyagent.org/docs/latest/#running-opa) on `PATH`.
Without OPA, the target prints a warning and exits `0` so `make ci` stays green.

## Documentation (canonical)

MkDocs pages (precise article tables + gates):

- [OPA, Rego, and OSCAL](../../docs/compliance/opa-rego-oscal.md)
- [EU Compliance OPA Audit](../../docs/compliance/eu-audit.md)
- [Latest audit results](../../docs/compliance/latest-results.md)
- [AI Act](../../docs/compliance/ai-act.md) · [CRA](../../docs/compliance/cra.md) ·
  [GDPR](../../docs/compliance/gdpr.md) · [NIS2](../../docs/compliance/nis2.md) ·
  [DORA](../../docs/compliance/dora.md) · [PLD](../../docs/compliance/pld.md)

Regenerate article tables after editing Rego catalogues:

```bash
make compliance-doc-tables
```

After each audit, full outcomes are published into
`docs/compliance/generated/` (`make compliance-doc-results` republishes
from the newest `reports/compliance/eu-audit/*/report.json` without re-eval).

## Layout

| Path | Role |
|------|------|
| `overrides.yaml` | Manual attestations (`null` = not assessed) |
| `collectors/input_generator.py` | Auto-scan → OPA input JSON |
| `run_audit.sh` | Orchestrator (OPA + OSCAL) |
| `report_generator.py` | HTML + JSON reports |
| `policies/` | Rego per regulation |
| `oscal/` | Catalogs, profile, components, SSP, schemas, `opa_to_oscal.py` |
| `scripts/gen_doc_tables.py` | Sync MkDocs article tables from Rego |
| `input/` | Generated inputs (gitignored except `.gitkeep`) |

## Output

`reports/compliance/eu-audit/<git-describe>/`:

- `report.html` / `report.json` — human aggregate (includes OSCAL section)
- `opa-*.json` — raw OPA summaries
- `oscal/assessment_results.json` — OSCAL Assessment Results
- `oscal/poam.json` — Plan of Action & Milestones

## AI Act categories

`input_generator.py` sets `determined_category` (overridable):

`UNACCEPTABLE` · `HIGH_RISK` · `LIMITED_RISK` · `MINIMAL_RISK` ·
`GPAI_STANDARD` · `GPAI_SYSTEMIC`

Articles that do not apply emit structured `NOT_MANDATORY` results (excluded
from the compliance score).

## OSCAL

Catalogs / profile / component definition / SSP live under `compliance/opa/oscal/`.
NIST production JSON Schema (v1.1.2) is vendored in
`compliance/opa/oscal/schemas/nist-v1.1.2/` from
[usnistgov/OSCAL](https://github.com/usnistgov/OSCAL/releases/tag/v1.1.2).
Regenerate catalogs after Rego changes: `make oscal-catalogs`.
Validate: `make oscal-validate` (also runs at the end of `make audit-compliance`).
Diff two runs: `make oscal-diff BASELINE=<ver> CURRENT=<ver>`.

MkDocs: [EU Compliance OPA Audit](../../docs/compliance/eu-audit.md).
