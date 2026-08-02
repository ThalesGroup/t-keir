# Quality gates

Hard fail conditions used by local `make ci` and (where noted) GitHub Actions.

## Thresholds

| Gate | Make target | Default | Where enforced |
|------|-------------|---------|----------------|
| Scoped line coverage | `make coverage` | ≥ **90%** (`COVERAGE_FAIL_UNDER`) | Local `ci`, Actions `ci.yml`, `release.yml` |
| Cyclomatic complexity | `make complexity` | average ≤ **7.0** on `thot/`; no grade-D functions (xenon/radon) | Local `ci`, Actions `ci.yml` |
| Licence policy | `make liccheck` | authorised list in `tkeir/liccheck.ini` | Local `ci`, Actions `ci.yml` |
| Lockfile drift | `make verify-lockfile` | `uv.lock` matches `pyproject.toml` | Local `ci`, Actions `ci.yml` |
| Secret hygiene | `make check-secrets` | no tracked secrets (see `.secrets-allowlist.yaml`) | Local `ci`, Actions `ci.yml` |
| Schema freshness | `make schemas-check` | Vespa schemas in sync | Local `ci`, Actions `ci.yml` |
| Lint / types | `make lint` / `typecheck` / HMI equivalents | clean | Local `ci`, Actions `ci.yml` |
| Docs build | `make docs-build` | MkDocs builds | Local `ci`, Actions `ci.yml` |
| SLSA level | `make slsa-level-gate` | ≥ **`SLSA_LEVEL`** (default **2**) | Local `ci` / `make slsa` (not PR `ci.yml`) |
| Cosign (optional) | `make sign-all` + `verify-signatures` | skipped if cosign missing unless `STRICT_SIGNING=1` | Local `ci` when cosign present |
| EU OPA audit | `make audit-compliance` | warns/skips if `opa` missing; otherwise policy results | Local `ci` / release |

## What PR CI does **not** gate

Actions `ci.yml` does **not** currently fail on:

- Trivy / OWASP / pip-audit findings (those run in `security.yml`)
- SLSA level
- Cosign signatures
- Integration / fuzz / BDD
- OPA compliance score

Use `make ci` locally (or tag a release) for the full matrix.

## Reading failures

| Symptom | Open |
|---------|------|
| Coverage below 90% | `reports/quality/coverage_report.txt` / `coverage.json` |
| Complexity gate | `reports/quality/radon_cc_gate.txt` or `radon_cc.json` |
| Licence deny | `liccheck` console + `tkeir/liccheck.ini` |
| Security CVEs | `reports/security/` after `make security-report` |
| SLSA below target | `reports/slsa/report.json` + `roadmap.md` (`make slsa-report`) |
| OPA red controls | [Compliance status](../compliance/status.md) / `reports/compliance/eu-audit/*/report.html` |

## Knobs

```bash
make coverage COVERAGE_FAIL_UNDER=85
make slsa SLSA_LEVEL=3          # aspirational; expect fail until hosted builder
make ci SKIP_INTEGRATION=1      # skip live-stack integration
make ci SKIP_SIGNING=1          # skip cosign even if installed
make ci STRICT_SIGNING=1        # require cosign
```
