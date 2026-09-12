# NIST OSCAL production JSON Schema (v1.1.2)

Canonical JSON Schema Draft-07 files from the NIST
[OSCAL](https://github.com/usnistgov/OSCAL) **v1.1.2** release. T-KEIR
`metadata.oscal-version` is `1.1.2` to match this pin.

What OSCAL is, and how it relates to OPA/Rego:
[OPA, Rego, and OSCAL](../../../docs/compliance/opa-rego-oscal.md).

| File | OSCAL model |
|------|-------------|
| `nist-v1.1.2/oscal_assessment-results_schema.json` | Assessment Results (SAR) |
| `nist-v1.1.2/oscal_poam_schema.json` | Plan of Action and Milestones |
| `nist-v1.1.2/oscal_assessment-plan_schema.json` | Assessment Plan |
| `nist-v1.1.2/oscal_catalog_schema.json` | Catalog |
| `nist-v1.1.2/oscal_profile_schema.json` | Profile |
| `nist-v1.1.2/oscal_ssp_schema.json` | System Security Plan |
| `nist-v1.1.2/oscal_component_schema.json` | Component Definition |

**Source:** [OSCAL 1.1.2 release assets](https://github.com/usnistgov/OSCAL/releases/tag/v1.1.2)
(`oscal_*_schema.json`). Do not hand-edit; replace the directory from a newer
NIST release and bump `oscal-version` in generated documents together.

**Validate** (end of `make audit-compliance`, or anytime):

```bash
make oscal-validate
# or
python3 compliance/opa/oscal/validate_oscal.py
```

NIST’s recommended CLI is [ajv-cli](https://github.com/usnistgov/OSCAL/blob/main/build/README.md)
(`ajv validate -s schema.json -d doc.json --extend-refs=true`). T-KEIR uses
the same schemas via Python `jsonschema` (Draft-07) so CI does not need
`oscal-cli` or Node. TokenDatatype in the official schema uses XML Schema
`\p{L}` / `\p{N}` classes; the validator maps those to ASCII tokens at
runtime and does **not** edit the NIST files.
