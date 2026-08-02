# GitHub Actions workflows

All workflows live under [`.github/workflows/`](https://github.com/ThalesGroup/t-keir/tree/main/.github/workflows).
Dependabot updates Actions / npm / pip / Docker weekly (`.github/dependabot.yml`).

## At a glance

| Workflow | File | When it runs | What you get |
|----------|------|--------------|--------------|
| **CI** | `ci.yml` | Every PR; push to `main` | Pass/fail only (no artefacts uploaded) |
| **Security & supply chain** | `security.yml` | Monday 04:17 UTC; `workflow_dispatch`; push to `main` when Makefile/scripts/lock/deploy change | **Artifact** `security-report` (`reports/security`, `reports/bom`, `reports/dependency-check`) |
| **Images** | `images.yml` | Push `main` / tags `v*`; PRs touching images/tkeir/hmi; manual | GHCR images; **Cosign keyless** on non-PR |
| **Helm charts** | `charts.yml` | PR/push when charts or `versions.lock.yaml` change | Lint + template render (logs; no upload) |
| **E2E** | `e2e.yml` | Daily 03:00 UTC; push when `deploy/` / cluster scripts change; manual | k3d cluster smoke (several steps allow failure) |
| **Release** | `release.yml` | Tags `v*`; manual | Full **`make ci`**, then GitHub Release with evidence packs |

---

## `ci.yml` — PR / main quality gate

**Jobs**

1. **`python-quality`** — `check-secrets`, `verify-lockfile`, `schemas-check`, `lint`, `typecheck`, `test-unit`, `coverage`, `liccheck`, `complexity`, `docs-build`
2. **`hmi-quality`** — `hmi-install`, `hmi-lint`, `hmi-typecheck`, `hmi-build`

**Not run here** (but are in local `make ci` / `release.yml`):

- integration / Hypothesis fuzz / BDD
- `pip-audit`, Trivy, OWASP Dependency-Check, BOM
- SLSA provenance / cosign
- EU OPA `audit-compliance`

---

## `security.yml` — supply-chain scans

Typical steps: `pip-audit`, `trivy`, `owasp-dependency-check`, `bom`, then `security-report`.

Download the workflow **artifact** named `security-report` from the Actions run, or regenerate locally:

```bash
make security-report
```

---

## `images.yml` — container build & sign

- Builds shared `tkeir-lib` then a matrix of service images.
- Pushes to `ghcr.io/<owner>/t-keir/<target>:<git-sha>` (non-PR).
- Signs with Cosign keyless OIDC on non-PR runs (`id-token: write`).

Local equivalents: `make images`, `make images-sign` (when configured).

---

## `charts.yml` — Helm

- `make helm-lint` (+ chart-testing when available)
- Template render smoke; Keycloak realm JSON sanity

---

## `e2e.yml` — cluster smoke

- Installs kubectl / helm / k3d
- Brings up a minimal cluster and runs smoke steps
- Several steps use `continue-on-error` — treat as **signal**, not a hard release gate

---

## `release.yml` — tagged release

On `v*` tags (or manual):

1. `make ci` (full gate)
2. `make changelog` (best effort)
3. `make audit-evidence` + `make annex-iv`
4. Creates a GitHub Release attaching:

   - `CHANGELOG.md`
   - `reports/evidence/**`
   - `reports/compliance/annex-iv/**`
   - `reports/bom/**`
   - `reports/security/**`

---

## Local vs Actions cheat sheet

| Concern | Local | Actions |
|---------|-------|---------|
| Unit + coverage | `make test-unit` / `make coverage` | `ci.yml` |
| Full gate | `make ci` | `release.yml` only |
| SBOM / Trivy / OWASP | `make security-report` | `security.yml` (+ Release assets) |
| Image sign | `make images-sign` / cosign | `images.yml` |
| Compliance HTML/JSON | `make audit-compliance` | via full `make ci` on release |
| Cluster smoke | `make cluster-*` / compose | `e2e.yml` |
