# EU Compliance OPA Audit Tool

Machine-checkable mappings from T-KEIR repository evidence to EU regulations
(AI Act, CRA, GDPR, NIS2, DORA, PLD). **Not legal advice.**

## Quick start

```bash
# From repository root
make audit-compliance
```

Requires [OPA](https://www.openpolicyagent.org/docs/latest/#running-opa) on `PATH`.
Without OPA, the target prints a warning and exits `0` so `make ci` stays green.

## Documentation (canonical)

MkDocs pages (precise article tables + gates):

- [EU Compliance OPA Audit](../../tkeir/docs/compliance/eu-audit.md)
- [Latest audit results](../../tkeir/docs/compliance/latest-results.md)
- [AI Act](../../tkeir/docs/compliance/ai-act.md) · [CRA](../../tkeir/docs/compliance/cra.md) ·
  [GDPR](../../tkeir/docs/compliance/gdpr.md) · [NIS2](../../tkeir/docs/compliance/nis2.md) ·
  [DORA](../../tkeir/docs/compliance/dora.md) · [PLD](../../tkeir/docs/compliance/pld.md)

Regenerate article tables after editing Rego catalogues:

```bash
make compliance-doc-tables
```

After each audit, full outcomes are published into
`tkeir/docs/compliance/generated/` (`make compliance-doc-results` republishes
from the newest `reports/compliance/eu-audit/*/report.json` without re-eval).

## Layout

| Path | Role |
|------|------|
| `overrides.yaml` | Manual attestations (`null` = not assessed) |
| `collectors/input_generator.py` | Auto-scan → OPA input JSON |
| `run_audit.sh` | Orchestrator (OPA + OSCAL) |
| `report_generator.py` | HTML + JSON reports |
| `policies/` | Rego per regulation |
| `oscal/` | Catalogs, profile, components, SSP, `opa_to_oscal.py` |
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
Regenerate catalogs after Rego changes: `make oscal-catalogs`.
Validate (optional): `make oscal-validate`. Diff two runs:
`make oscal-diff BASELINE=<ver> CURRENT=<ver>`.

MkDocs: [EU Compliance OPA Audit](../../tkeir/docs/compliance/eu-audit.md).
