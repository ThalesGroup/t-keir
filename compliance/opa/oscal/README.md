# OSCAL layer (EU compliance)

Open Security Controls Assessment Language documents for T-KEIR.

| Path | Purpose |
|------|---------|
| `catalogs/` | One catalog per regulation (generated from Rego) |
| `profiles/tkeir_eu_profile.json` | Imports all catalogs + parameters |
| `component-definitions/tkeir_components.json` | Component → control-id → evidence |
| `ssp/tkeir_ssp.json` | System Security Plan template |
| `assessments/assessment_plan.json` | Assessment plan (OPA automated) |
| `opa_to_oscal.py` | Bridge OPA JSON → Assessment Results + POA&M |
| `gen_oscal_catalogs.py` | Regenerate catalogs (`make oscal-catalogs`) |

Canonical narrative: `tkeir/docs/compliance/eu-audit.md`.
