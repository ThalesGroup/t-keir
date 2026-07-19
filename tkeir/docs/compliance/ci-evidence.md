# CI and evidence pipeline

This page maps T-KEIR's repository checks to the evidence they produce.
It describes engineering controls, not a legal attestation.

Those artefacts are also **inputs** to the OPA EU compliance audit
(`make audit-compliance`) — see [EU Compliance OPA Audit](eu-audit.md).

## Quality gates

The default repository gate is `make ci`.

It runs:

- secret hygiene (`make check-secrets`) — blocks tracked `.env`, credential
  filenames, and high-confidence secret patterns (see `.secrets-allowlist.yaml`)
- lockfile drift detection (`make verify-lockfile`)
- Python lint / typecheck / tests / coverage
- HMI lint / typecheck / build
- dependency license review
- complexity checks
- dependency and filesystem security scans
- SBOM / AIBOM generation
- documentation build
- Trivy / OWASP Dependency-Check
- **EU compliance OPA audit** (`make audit-compliance`) as the final additive
  step — skipped with a warning if `opa` is not on `PATH`

## Security artifacts

These commands produce auditable outputs consumed by OPA `input.evidence`:

| Command | Evidence | Typical OPA keys |
|---------|----------|------------------|
| `make pip-audit` | Python CVE results in CI logs | `pip_audit_run_in_ci` |
| `make trivy` | `reports/security/trivy-*.txt` | `trivy_report_present` |
| `make owasp-dependency-check` | `reports/dependency-check/` | `owasp_dc_present` |
| `make bom` | `reports/bom/` CycloneDX SBOM + AIBOM | `sbom_cyclonedx_present`, `aibom_present` |
| `make security-report` | `reports/security/manifest.json` | `security_manifest_present` |
| `make annex-iv` | `reports/compliance/annex-iv/` | `annex_iv_dir_non_empty` |
| `make audit-evidence` | `reports/evidence/<version>/` | `audit_evidence_dir_non_empty` |
| `make audit-compliance` | `reports/compliance/eu-audit/<version>/` (+ `oscal/`) | OPA HTML/JSON + OSCAL AR/POA&M |

## CI workflows

The GitHub Actions layer separates concerns:

| Workflow | Role |
|----------|------|
| `ci.yml` | quality gate for Python + HMI + docs |
| `charts.yml` | Helm dependency update, lint, and template rendering |
| `security.yml` | scheduled or on-demand dependency / SBOM / container-config scans |

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
