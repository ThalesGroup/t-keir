# OSCAL layer (EU compliance)

[OSCAL](https://github.com/usnistgov/OSCAL) (NIST Open Security Controls
Assessment Language) is the **exchange format**, not the policy engine.
OPA/Rego decide pass / fail / not-mandatory; this directory holds catalogs,
profile, SSP, assessment plan, and the bridge that turns OPA JSON into
Assessment Results + POA&M.

Primer: [OPA, Rego, and OSCAL](../../../docs/compliance/opa-rego-oscal.md).
Operational audit: [EU Compliance OPA Audit](../../../docs/compliance/eu-audit.md).

| Path | Purpose |
|------|---------|
| `catalogs/` | One catalog per regulation (generated from Rego) |
| `profiles/tkeir_eu_profile.json` | Imports all catalogs + parameters |
| `component-definitions/tkeir_components.json` | Component → control-id → evidence |
| `ssp/tkeir_ssp.json` | System Security Plan template |
| `assessments/assessment_plan.json` | Assessment plan (OPA automated) |
| `schemas/nist-v1.1.2/` | NIST OSCAL 1.1.2 production JSON Schema |
| `opa_to_oscal.py` | Bridge OPA JSON → Assessment Results + POA&M |
| `validate_oscal.py` | Draft-07 validation against the NIST schemas |
| `gen_oscal_catalogs.py` | Regenerate catalogs (`make oscal-catalogs`) |

Canonical narrative: `docs/compliance/opa-rego-oscal.md` (concepts) and
`docs/compliance/eu-audit.md` (how to run).
