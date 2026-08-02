# Reports catalog

Every durable CI / quality artefact and the Make target that produces it.
Directories under `reports/` and `coverage-reports/` are gitignored unless noted.

## How to regenerate

```bash
make coverage            # quality coverage artefacts
make complexity-report   # radon JSON/text
make pip-licenses        # licence inventory
make security-report     # unified security index + copies
make bom                 # CycloneDX SBOM + AIBOM
make slsa-report         # SLSA provenance + roadmap
make test-integration-ci # integration junit
make test-bdd-ci         # BDD json + junit
make fuzz-report         # fuzz summary
make audit-compliance    # EU OPA pack + MkDocs status pages
make audit-evidence      # release evidence tree
make annex-iv            # Annex IV pack
make docs-build          # site/ + refresh quality dashboard
```

---

## Quality & coverage

| Make target | Primary outputs |
|-------------|-----------------|
| `make coverage` | `coverage-reports/coverage.xml` |
| | `reports/quality/coverage_report.txt` |
| | `reports/quality/coverage.json` |
| | `reports/quality/coverage_summary.txt` |
| | `reports/quality/coverage.xml` (copy) |
| `make complexity` | Gate (fail on threshold) + `reports/quality/radon_cc_gate.txt` |
| `make complexity-report` | `reports/quality/radon_cc.json` |
| | `reports/quality/radon_mi.json` / `radon_mi.txt` |
| | `reports/quality/radon_cc_summary.txt` |
| `make pip-licenses` / `license-report` | `reports/quality/licenses.{json,md,csv}` |
| `make quality-docs` | Rewrites [docs/quality/index.md](../quality/index.md) from the files above |
| `make docs-build` | `site/` (+ runs `quality-docs`) |
| `make docs-pdf` | `output/docs/tkeir-docs.pdf` |

**Gate:** scoped line coverage ≥ `COVERAGE_FAIL_UNDER` (default **90%**). See [Quality gates](gates.md).

---

## Security & BOM

| Make target | Primary outputs |
|-------------|-----------------|
| `make bom` / `sbom` / `aibom` | `reports/bom/tkeir.cdx.json` |
| | `reports/bom/tkeir.cdx.xml` |
| | `reports/bom/views/*.cdx.json` |
| `make trivy` | `reports/security/trivy-*.txt` (+ exported requirements) |
| `make owasp-dependency-check` | `reports/dependency-check/` |
| `make pip-audit` | Console / CI logs (no dedicated file) |
| `make security-report` | Runs audits above, then: |
| | `reports/security/index.txt` |
| | `reports/security/manifest.json` |
| | copies of bom + dependency-check under `reports/security/` |

Uploaded by Actions: **`security.yml`** artefact `security-report`. Also attached on **`release.yml`**.

---

## Supply chain (SLSA / signatures)

| Make target | Primary outputs |
|-------------|-----------------|
| `make slsa-provenance` | `reports/slsa/provenance.json` |
| `make slsa-assess` / `slsa-report` | `reports/slsa/report.json` |
| | `reports/slsa/roadmap.md` (path to next SLSA level) |
| `make slsa` | Full pipeline + level gate (`SLSA_LEVEL`, default **2**) |
| `make sign-all` | `reports/signatures/wheel.bundle` |
| | `reports/signatures/sbom.bundle` |
| | `reports/signatures/provenance.bundle` |
| `make verify-signatures` | Verifies the bundles above |

Cosign must be installed (`brew install cosign` on macOS). See `make check-supply-tools`.

---

## Tests beyond unit

| Make target | Primary outputs |
|-------------|-----------------|
| `make test-unit` | Console (suites under `tests/unittests/`) |
| `make test-functional` | Console (`tests/functional_tests/`) |
| `make test-integration-ci` | `reports/integration/junit.xml` |
| `make test-fuzz-hypothesis` | Console |
| `make test-fuzz-radamsa` | `reports/fuzzing/radamsa-summary.json` (+ mutants) |
| `make test-fuzz-atheris` | Linux only; crash artefacts under `reports/fuzzing/` |
| `make fuzz-report` | `reports/fuzzing/summary.json` |
| `make test-bdd` | Console |
| `make test-bdd-ci` | `reports/bdd/behave.json` + JUnit under `reports/bdd/` |
| `make bdd-report` | Optional Allure HTML under `reports/bdd/allure-html/` |

---

## Compliance & evidence

| Make target | Primary outputs |
|-------------|-----------------|
| `make compliance-input` | `compliance/opa/input/generated_*.json` |
| `make audit-compliance` | `reports/compliance/eu-audit/<git-describe>/` |
| | `report.html`, `report.json`, `oscal/…` |
| | refreshes [compliance status](../compliance/status.md) pages |
| `make audit-evidence` | `reports/evidence/<version>/` |
| `make annex-iv` | `reports/compliance/annex-iv/` |
| `make lineage-report` | Lineage script over ingest manifests |

OPA mapping details: [CI and evidence pipeline](../compliance/ci-evidence.md).

---

## Evaluation

| Make target | Primary outputs |
|-------------|-----------------|
| `make beir-eval` / `eval` | `docs/evaluation_report.md` + `reports/beir/` |
| `make generate-eval` | `docs/evaluation_generate_report.md` + `reports/generate/` |

---

## Runtime audit (not under `reports/`)

| Make target | Where |
|-------------|--------|
| `make audit-report` | Rendered via audit API / `workspace/audit` |
| `make audit-summary` | Hot store summary |
| `make audit-verify` | Hash chain / WORM check under `workspace/audit` |
| `make audit-archive` | Export to `workspace/audit/worm` |

See [deployment/audit.md](../deployment/audit.md).

---

## Variable overrides

| Variable | Default | Used by |
|----------|---------|---------|
| `QUALITY_REPORT_DIR` | `reports/quality` | coverage, radon, licences |
| `COVERAGE_REPORT_DIR` | `coverage-reports` | Cobertura XML |
| `SECURITY_REPORT_DIR` | `reports/security` | trivy / security-report |
| `BOM_REPORT_DIR` | `reports/bom` | CycloneDX |
| `INTEGRATION_REPORT_DIR` | `reports/integration` | junit |
| `FUZZ_REPORT_DIR` | `reports/fuzzing` | fuzz artefacts |
| `BDD_REPORT_DIR` | `reports/bdd` | behave / junit |
| `SLSA_REPORT_DIR` | `reports/slsa` | provenance + roadmap |
| `COSIGN_BUNDLE_DIR` | `reports/signatures` | cosign bundles |
| `COVERAGE_FAIL_UNDER` | `90` | coverage gate |
| `SLSA_LEVEL` | `2` | SLSA gate |
