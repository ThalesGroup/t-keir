# CI and evidence pipeline

This page maps repository checks to **OPA evidence keys** used by the EU
compliance audit. For the full catalogue of GitHub Actions, report directories,
and quality thresholds, start here:

| Guide | Contents |
|-------|----------|
| [CI, reports & Actions](../ci/index.md) | Local `make ci` vs PR CI; report tree |
| [Workflows](../ci/workflows.md) | All six Actions workflows + artefacts |
| [Reports catalog](../ci/reports-catalog.md) | Make target → output path |
| [Quality gates](../ci/gates.md) | Coverage / complexity / SLSA thresholds |

Those artefacts are **inputs** to `make audit-compliance` — see
[EU Compliance OPA Audit](eu-audit.md).

## Quality gates (summary)

The default local gate is `make ci`. PR Actions (`ci.yml`) run a **subset**
(unit + coverage + lint/types/docs). Full security, SLSA, and OPA run locally
or on release — see [workflows](../ci/workflows.md).

`make ci` includes:

- secret hygiene (`make check-secrets`)
- lockfile drift (`make verify-lockfile`)
- Python lint / typecheck / unit + functional tests / coverage
- optional integration / Hypothesis fuzz / BDD
- HMI lint / typecheck / build
- licence review + complexity
- dependency and filesystem security scans
- SBOM / AIBOM + Trivy / OWASP
- SLSA provenance (+ cosign when installed)
- documentation build
- **EU compliance OPA audit** (`make audit-compliance`) — skipped with a
  warning if `opa` is not on `PATH`

## Security artefacts → OPA keys

| Command | Evidence | Typical OPA keys |
|---------|----------|------------------|
| `make pip-audit` | Python CVE results in CI logs | `pip_audit_run_in_ci` |
| `make trivy` | `reports/security/trivy-*.txt` | `trivy_report_present` |
| `make owasp-dependency-check` | `reports/dependency-check/` | `owasp_dc_present` |
| `make bom` | `reports/bom/` CycloneDX SBOM + AIBOM | `sbom_cyclonedx_present`, `aibom_present` |
| `make security-report` | `reports/security/manifest.json` | `security_manifest_present` |
| `make complexity-report` | `reports/quality/radon_cc.json` + `radon_cc_summary.txt` | CC average ≤ 7.0 on `thot/`, zero grade-D functions |
| `make coverage` | `coverage-reports/coverage.xml` + `reports/quality/coverage_*.*` | Scoped line coverage ≥ `COVERAGE_FAIL_UNDER` (default 90%) |
| `make pip-licenses` | `reports/quality/licenses.json` + `licenses.md` | Full dependency licence inventory |
| `make annex-iv` | `reports/compliance/annex-iv/` | `annex_iv_dir_non_empty` |
| `make audit-evidence` | `reports/evidence/<version>/` | `audit_evidence_dir_non_empty` |
| `make audit-compliance` | `reports/compliance/eu-audit/<version>/` (+ `oscal/`) | OPA HTML/JSON + OSCAL AR/POA&M |
| `make slsa-report` | `reports/slsa/report.json` + `roadmap.md` | SLSA level assessment |

## Scope limits

Current CI hardening is aimed at software development and release hygiene.
It does **not** replace:

- runtime admission control
- production secret managers
- cluster-side image verification
- a legal conformity assessment or notified-body opinion

OPA results are **engineering evidence mappings**. Attestations that cannot be
inferred from the repo remain in `compliance/opa/overrides.yaml` (`null` until
assessed).
