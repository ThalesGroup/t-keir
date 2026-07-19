# EU Compliance OPA Audit

> **Not legal advice.** This page describes the machine-checkable audit tool
> under `compliance/opa/`. It maps repository evidence and manual attestations
> to EU regulation articles via OPA (Open Policy Agent).

## Why it exists

Earlier compliance pages listed only a few illustrative articles. The OPA
policies cover **every article** wired in the catalogues (including obligations
T-KEIR does not implement). When an article does not apply to the current
deployment context or AI Act category, the policy emits a structured
`NOT_MANDATORY` result instead of a violation or silence.

| Package | Regulation | Policy file | Approx. checks |
|---------|------------|-------------|----------------|
| `eu.ai_act` | AI Act Reg. (EU) 2024/1689 | `compliance/opa/policies/ai_act/ai_act.rego` | Art.5(1)(a–g) + 102 catalogue rows |
| `eu.cra` | CRA Reg. (EU) 2024/2847 | `…/cra/cra.rego` | 47 |
| `eu.gdpr` | GDPR Reg. (EU) 2016/679 | `…/gdpr/gdpr.rego` | 43 |
| `eu.nis2` | NIS2 Dir. (EU) 2022/2555 | `…/nis2/nis2.rego` | 25 |
| `eu.dora` | DORA Reg. (EU) 2022/2554 | `…/dora/dora.rego` | 38 |
| `eu.pld` | PLD Dir. (EU) 2024/2853 | `…/pld/pld.rego` | 18 |

Shared helpers: `compliance/opa/policies/lib/common.rego` (`violation`, `pass`,
`not_mandatory`, `score`).

Per-regulation article tables (gates + evidence anchors):

- [AI Act](ai-act.md)
- [CRA](cra.md)
- [GDPR](gdpr.md)
- [NIS2](nis2.md)
- [DORA](dora.md)
- [PLD](pld.md)

## How to run

```bash
# From repository root (requires `opa` on PATH)
make audit-compliance
```

Aliases: `make compliance-report` · input-only: `make compliance-input` ·
docs-only republish: `make compliance-doc-results`.

| Step | What happens |
|------|----------------|
| 1 | `input_generator.py` scans the repo + merges `compliance/opa/overrides.yaml` |
| 2 | Writes `compliance/opa/input/generated_<timestamp>.json` (gitignored) |
| 3 | `opa check --v0-compatible` on `compliance/opa/policies/` |
| 4 | `opa eval` of `data.eu.<reg>.summary` for each regulation |
| 5 | `opa_to_oscal.py` → OSCAL Assessment Results + POA&M under `…/oscal/` |
| 6 | `report_generator.py` → HTML + JSON (includes OSCAL download links + posture trend) |
| 7 | `gen_doc_results.py` → full outcomes into `tkeir/docs/compliance/generated/` |

Without OPA:

```text
[eu-audit] WARNING: opa not found on PATH — skipping EU compliance audit.
```

Exit code **0** so `make ci` stays green. Set `COMPLIANCE_STRICT=1` to fail the
orchestrator when the aggregated report still has gaps.

`make ci` runs **`audit-compliance` after** SBOM / Trivy / OWASP evidence is
produced, then rebuilds MkDocs so [Latest audit results](latest-results.md)
embeds the full article outcomes from that run.

## OSCAL layer (regulator / GRC exchange)

OPA answers “does control X pass **today**?”. **OSCAL** (NIST Open Security
Controls Assessment Language, 1.1.2) answers the auditor questions: which
exact requirement, which component implements it, what evidence, and what
changed over time.

| Artefact | Path | Role |
|----------|------|------|
| Catalogs | `compliance/opa/oscal/catalogs/eu_*_catalog.json` | Every article as an OSCAL `control` (`ai-act-art-12-1`, …) |
| Profile | `…/profiles/tkeir_eu_profile.json` | Imports all six catalogs; parameters `ai-act-category`, `nis2-entity-type`, … |
| Component Definition | `…/component-definitions/tkeir_components.json` | governor / audit / pipeline / Keycloak / CI / NetworkPolicy → `control-id` + evidence |
| SSP | `…/ssp/tkeir_ssp.json` | System Security Plan template |
| Assessment Plan | `…/assessments/assessment_plan.json` | Maps `make audit-compliance` to OSCAL tasks |
| Assessment Results | `reports/compliance/eu-audit/<ver>/oscal/assessment_results.json` | OPA pass/fail/NA → observations + findings |
| POA&M | `…/oscal/poam.json` | Open findings with remediation milestones |

Bridge: `compliance/opa/oscal/opa_to_oscal.py` (deterministic **UUID v5** so
diffs show real posture changes, not regenerated ids).

```bash
make audit-compliance          # produces HTML + OSCAL under reports/…
make oscal-catalogs            # regenerate catalogs from Rego
make oscal-validate            # oscal-cli if installed; else warning + exit 0
make oscal-diff BASELINE=… CURRENT=…   # posture delta between two runs
```

Control id join key (catalog ↔ profile ↔ SSP ↔ AR):

```text
Art.12(1)  →  ai-act-art-12-1
AnnexI.PartI.1(a)  →  cra-annex-i-parti-1-a
```

Pipeline:

```text
Repo artefacts → input_generator → OPA eval
                                      ↓
                         opa_to_oscal.py → assessment_results.json + poam.json
                                      ↓
                         report.html (human) + GRC ingestion (machine)
```

See also `compliance/opa/README.md` and the component definition for
`evidence-artifact` / `test-command` props per control.

## Result model (every policy)

Each `.rego` package exposes four sets plus an aggregate:

| Rule set | Meaning |
|----------|---------|
| `violations[v]` | Article **applies** and control **not met** |
| `passed[p]` | Article **applies** and control **met** |
| `not_applicable[n]` | Article **does not apply** → status `NOT_MANDATORY` |
| `summary` | Counts, score, lists, `articles_covered` |
| `allow` | `count(violations) == 0` |

`NOT_MANDATORY` object shape:

```json
{
  "status": "NOT_MANDATORY",
  "regulation": "AI_ACT",
  "article": "Art.9(1)",
  "reason": "Applies only to HIGH_RISK AI systems (current category: LIMITED_RISK)"
}
```

**Compliance score** (per regulation and overall):

\[
\mathrm{score} = \mathrm{round}\left(100 \times \frac{|passed|}{|passed| + |violations|}\right)
\]

`NOT_MANDATORY` rows are **excluded** from the denominator so they do not
inflate the score.

### Tri-state evidence semantics

| Value | Meaning in generated input |
|-------|----------------------------|
| `true` | Assessed present (file found / pattern matched / attestation `true`) |
| `false` | Assessed absent (scan ran; artefact missing) |
| `null` | Not yet assessed (manual attestation only — never invented as `false`) |

In Rego, controls use “explicitly true” checks (`x == true`). Both `false` and
`null` fail a required control when the article applies.

## AI Act category gate (classification first)

Before evaluating Title III / IV / V obligations, `input_generator.py` computes
`ai_act.classification.determined_category` (overridable in `overrides.yaml`):

```text
any prohibited_practices[*] == true     → UNACCEPTABLE
is_gpai_model && gpai_systemic_risk     → GPAI_SYSTEMIC
is_gpai_model                           → GPAI_STANDARD
annex_iii_applies
  OR safety_component_regulated_product → HIGH_RISK
intended_interaction_with_natural_persons
  OR processes_biometric_data           → LIMITED_RISK
else                                    → MINIMAL_RISK
```

| Category | What is evaluated | What becomes `NOT_MANDATORY` |
|----------|-------------------|------------------------------|
| `UNACCEPTABLE` | Art.5(1)(a–g) only (CRITICAL if practice true) | **All other** AI Act articles |
| `HIGH_RISK` | Art.6–29 (with sub-gates), Art.50, Art.72–73, Art.5 | GPAI Art.53–55; importer/distributor/notified-body when role unset |
| `LIMITED_RISK` | Art.5, Art.50 (transparency), Art.72–73 | Art.6–29, Art.33–43, Art.53–55 |
| `MINIMAL_RISK` | Art.5, Art.72–73 (if `is_ai_system`) | Art.6–29, Art.50, Art.53–55 |
| `GPAI_STANDARD` | Art.5, Art.53–54, Art.72–73 | High-risk Title III; Art.55; Art.50 |
| `GPAI_SYSTEMIC` | Art.5, Art.53–55, Art.72–73 | High-risk Title III; Art.50 |

Sub-gates inside HIGH_RISK:

| Gate id | Extra condition |
|---------|-----------------|
| `high_risk_biometric` | `processes_biometric_data == true` (Art.12(4), Art.14(4)) |
| `high_risk_importer` | `product.role == "importer"` (Art.23) |
| `high_risk_distributor` | `product.role == "distributor"` (Art.24) |
| `high_risk_notified_body` | `attestation.conformity_assessment.uses_notified_body == true` |
| `limited_or_high_emotion` | emotion-recognition practice / feature |
| `limited_or_high_biometric_cat` | biometric categorisation practice / feature |

## Scope gates (other regulations)

| Regulation | Scope field | Out-of-scope behaviour |
|------------|-------------|------------------------|
| NIS2 | `nis2.entity_type` ∈ `ESSENTIAL` \| `IMPORTANT` \| `OUT_OF_SCOPE` | All NIS2 articles `NOT_MANDATORY` when `OUT_OF_SCOPE` |
| DORA | `dora.in_scope` | All DORA articles `NOT_MANDATORY` when `false` |
| PLD | `pld.in_scope` | All PLD articles `NOT_MANDATORY` when `false` |
| CRA | Always evaluated (product + manufacturer contexts); Art.21/22 gated by `product.role` | Importer/distributor articles `NOT_MANDATORY` unless role matches |
| GDPR | Always evaluated (processing assumed for the platform) | Individual articles still use attestation/`null` |

## Auto-detected evidence (T-KEIR paths)

`collectors/input_generator.py` sets `input.evidence.*` from **exact** repository
paths (missing → `false`, never `null`):

| Evidence key | Detection |
|--------------|-----------|
| `sbom_cyclonedx_present` | `reports/bom/bom.json` or `reports/bom/*.json` |
| `aibom_present` | `reports/bom/*aibom*` |
| `trivy_report_present` | `reports/security/trivy-*.txt` |
| `pip_audit_run_in_ci` | `pip-audit` in `.github/workflows/` or `Makefile` |
| `owasp_dc_present` | `reports/dependency-check/` or `reports/security/dependency-check/` |
| `security_manifest_present` | `reports/security/manifest.json` |
| `images_signed` | `cosign` / `images-sign` in workflows or Makefile |
| `versions_lock_present` | `deploy/versions.lock.yaml` |
| `security_md_present` | `SECURITY.md` |
| `changelog_present` | `CHANGELOG.md` |
| `annex_iv_dir_non_empty` | `reports/compliance/annex-iv/` non-empty |
| `audit_evidence_dir_non_empty` | `reports/evidence/` non-empty |
| `beir_eval_report_present` | `tkeir/docs/evaluation_report.md` |
| `action_schema_present` | `tkeir/thot/action/schemas/action.v1.json` |
| `governor_flags_present` | `tkeir/thot/governor/flags.py` |
| `governor_approvals_present` | `tkeir/thot/governor/approvals.py` |
| `governor_tokens_present` | `tkeir/thot/governor/tokens.py` |
| `kill_switch_runbook_present` | `tkeir/docs/runbooks/kill-switch.md` |
| `hmi_admin_page_present` | `tkeir-hmi/app/admin/page.tsx` |
| `privacy_py_present` | `tkeir/thot/audit/privacy.py` |
| `ingest_manifest_schema` | `tkeir/thot/ingest/schemas/ingest.manifest.v1.json` |
| `audit_worm_retention_set` | `AUDIT_WORM_RETENTION_DAYS` in `deploy/compose/.env.example` |
| `incident_runbook_present` | `tkeir/docs/runbooks/incident.md` |
| `networkpolicy_template` | `deploy/charts/tkeir/templates/networkpolicy.yaml` |
| `keycloak_realm_present` | `deploy/keycloak/realm-tkeir.json` |
| `values_secure_present` | `deploy/charts/tkeir/values-secure.yaml` |
| `compose_auth_profile` | `auth` under `deploy/compose/` |
| `observability_profile` | `grafana` / `prometheus` under `deploy/compose/` |
| `rollback_target_in_makefile` | `rollback-index` in `Makefile` |
| `audit_verify_target` | `audit-verify` in `Makefile` |
| `correlation_id_in_code` | `X-Correlation-Id` under `tkeir/` |

Manual fields live only in `compliance/opa/overrides.yaml` (see comments in
that file).

## Output artefacts

```text
reports/compliance/eu-audit/<git-describe>/
  input.json          # copy of OPA input
  opa-ai_act.json     # raw opa eval of data.eu.ai_act.summary
  opa-cra.json
  opa-gdpr.json
  opa-nis2.json
  opa-dora.json
  opa-pld.json
  report.json         # aggregated summary
  report.html         # human-readable report
```

## Tests

```bash
cd tkeir && uv run --python 3.11 pytest tests/unittests/compliance/ -q
```

Tests skip when `opa` is absent. Fixtures cover `MINIMAL_RISK`, `HIGH_RISK`
gaps, `UNACCEPTABLE` / Art.5, and `GPAI_SYSTEMIC`.

## Regenerating article tables in MkDocs

Article tables embedded via snippets under `tkeir/docs/compliance/generated/`
are produced from the Rego catalogues:

```bash
python3 compliance/opa/scripts/gen_doc_tables.py
# or: make compliance-doc-tables
```

Re-run after editing any `*.rego` catalogue so documentation stays aligned with
the policies.

## Publishing audit results into MkDocs

After each successful OPA run, `gen_doc_results.py` writes:

| Fragment | Contents |
|----------|----------|
| `generated/latest_results.md` | Overall score + every regulation’s full outcomes |
| `generated/<reg>_results.md` | Per-regulation violations / passed / `NOT_MANDATORY` |
| `generated/latest_report.json` | Copy of aggregate `report.json` for in-repo diffs |
| `generated/gdpr_reviewer_checklist.md` | GDPR checkbox list (legal vs automatic) |
| `generated/cra_reviewer_checklist.md` | CRA checkbox list (legal vs automatic) |
| `generated/legal_review_checklist.md` | Combined GDPR/CRA reviewer summary |

Embedded by [Latest audit results](latest-results.md) and
[Legal / reviewer checklist](legal-review-checklist.md). Republish without
re-evaluating:

```bash
make compliance-doc-results
```

## Related

- Tool tree: `compliance/opa/` (see `compliance/opa/README.md` at the repo root)
- [Latest audit results](latest-results.md)
- [CI and evidence pipeline](ci-evidence.md)
- [Zero to Hero §8](../zero_to_hero.md#8-p4-platform--evidence)
