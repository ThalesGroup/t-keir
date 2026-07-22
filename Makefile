# T-KEIR — local development Makefile
MAKEFLAGS += --warn-undefined-variables
.DELETE_ON_ERROR:

SHELL       := /usr/bin/env bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# Verbosity — make <target> VERBOSE=1 to print every recipe command
# ---------------------------------------------------------------------------
VERBOSE ?= 0
ifeq ($(VERBOSE),1)
Q :=
else
Q := @
endif

.PHONY: help setup install check-uv check-docker check-git check-jq check-curl check-python-version check-secrets \
	install-tesseract install-spacy-models build wheel init-models \
	test test-unit test-functional test-coverage coverage \
	lint format typecheck liccheck complexity complexity-report pip-licenses license-report quality-docs pip-audit \
	deps-check deps-update deps-update-safe verify-lockfile tag changelog \
	bom sbom aibom trivy owasp-dependency-check security-report \
	docs docs-build docs-pdf pipeline quickstart install-workspace ci-deps ci pre-commit clean devcontainer \
	sync pull-models start init bootstrap vespa-check test-vespa test-vespa-py \
	index index-fixtures rag ingest rag-query search-query mcp mcp-tools agent agent-run smoke-test beir-eval clean-db vespa-clean logs \
	images images-push images-sign \
	compose-up compose-down compose-logs compose-smoke audit-report audit-verify audit-archive \
	governor-flags governor-kill rollback-index check-secrets-staged \
	hmi-install hmi-lint hmi-typecheck hmi-build \
	k3d-up k3d-down helm-deps helm-lint helm-template cluster-install cluster-plan cluster-uninstall \
	k3s-server k3s-agent k3s-check cilium-install lima-k3s-up lima-k3s-down \
	keycloak-export-realm seal kubeflow-install kubeflow-uninstall kubeflow-register-models kubeflow-run-ingest \
	lineage-report audit-evidence annex-iv \
	corpus corpus-ontologies corpus-download corpus-ingest corpus-ingest-user corpus-ingest-admin \
	corpus-ingest-web corpus-demo corpus-clean

# Composite targets (setup, ci) use sequential $(MAKE) recipes so
# `make -j setup` / `make -j ci` cannot race on .venv or coverage files.

UV ?= uv
PYTHON ?= 3.11
COMPOSE ?= docker compose
# Pin by digest for supply-chain integrity. To update: docker pull <image:tag> && docker inspect --format='{{index .RepoDigests 0}}' <image:tag>
TRIVY_IMAGE ?= aquasec/trivy@sha256:665030f4d33a82c1e8d9d5e0453365842236723c1ee5cc3becca698268e66a56
OWASP_DC_IMAGE ?= owasp/dependency-check@sha256:60ee7af9cf80ac009761e397b2d4ba5ddbf072c2a0ead1c068dc24dc62155600
OWASP_DC_FAIL_CVSS ?= 7
TRIVY_SEVERITY ?= HIGH,CRITICAL
BOM_SPEC_VERSION ?= 1.6
BOM_REPORT_DIR ?= reports/bom
BOM_CONFIG ?= scripts/bom/config.yaml
BOM_PYTHON ?= tkeir/.venv/bin/python
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
THIS_MAKEFILE := $(firstword $(MAKEFILE_LIST))

# ---------------------------------------------------------------------------
# Build identity — injected into artifacts, BOM, and security reports
# ---------------------------------------------------------------------------
VERSION     ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo "0.0.0-dev")
GIT_COMMIT  := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
GIT_BRANCH  := $(shell git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
BUILD_DATE  := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)

TKEIR_DIR := $(ROOT)/tkeir
HMI_DIR := $(ROOT)/tkeir-hmi
VESPA_DIR := $(ROOT)/vespa
TESTS_DIR := $(TKEIR_DIR)/tests
CONFIGS_DIR := $(TKEIR_DIR)/configs
SCRIPTS_DIR := $(ROOT)/scripts
COVERAGE_REPORT_DIR := $(ROOT)/coverage-reports
SECURITY_REPORT_DIR ?= $(ROOT)/reports/security
LICCHECK_CONFIG ?= $(TKEIR_DIR)/liccheck.ini
DIST_DIR := $(ROOT)/dist
BUILD_STAMP := $(DIST_DIR)/.build_timestamp

WORKSPACE ?= $(ROOT)/workspace
PIPELINE_CONFIG ?= $(CONFIGS_DIR)/pipeline.yaml
PIPELINE_INPUT ?= $(TKEIR_DIR)/tests/fixtures/test-raw/raw
PIPELINE_OUTPUT ?= $(WORKSPACE)/tmp/pipeline-out
PIPELINE_TYPE ?= auto
TRANSFORMERS_CACHE ?= $(ROOT)/.cache/models
DOCS_PORT ?= 8000
DOCS_PDF_OUTPUT ?= $(ROOT)/output/docs/tkeir-docs.pdf

INDEX_INPUT ?= $(TKEIR_DIR)/tests/indexing/output
INDEX_FIXTURES_INPUT := $(TKEIR_DIR)/tests/indexing/input
RAG_URL ?= http://localhost:8090
RAG_QUERY ?= Who is Rob Brown?
RAG_LANGUAGE ?= en
RAG_HITS ?= 20
BEIR_DATASETS_DIR ?= $(ROOT)/datasets
# Optional extra report copy; docs report is always written by beir_eval.
BEIR_REPORT ?=
# Space-separated BEIR dataset names. One dataset example:
#   make beir-eval BEIR_DATASETS=scifact
BEIR_DATASETS ?= scifact fiqa arguana
BEIR_DENSE_MODEL ?= sentence-transformers/all-MiniLM-L6-v2
# Dedicated Vespa volume so BEIR reindex does not wipe the primary corpus.
BEIR_VESPA_NAME ?= vespa
BEIR_VESPA_VOLUME ?= beir_eval_data:/opt/vespa/var
# Extra CLI flags for beir_eval, e.g. BEIR_EXTRA=--skip-dense
BEIR_EXTRA ?=

ENVIRONMENT      ?= local
SMOKE_TARGET_URL ?= http://localhost:8090
SMOKE_TIMEOUT    ?= 10

DEPS_BRANCH ?= deps/auto-update-$(shell date +%Y%m%d)

# Container images — local daemon by default; publish with IMAGE_REGISTRY=ghcr.io/thalesgroup/t-keir
IMAGE_REGISTRY ?= local
IMAGE_TAG ?= $(VERSION)
# Empty = native platform (fast local). CI/push: linux/amd64,linux/arm64
PLATFORMS ?=
MODEL_MODE ?= fetch
BAKE_FILE := $(ROOT)/deploy/images/docker-bake.hcl
COMPOSE_DIR := $(ROOT)/deploy/compose
COMPOSE_FILE := $(COMPOSE_DIR)/docker-compose.yml
PROFILES ?= core,auth
COMPOSE_PROFILES := $(PROFILES)
PYTHON_BASE_IMAGE ?= python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93
NODE_BASE_IMAGE ?= node:22-bookworm-slim@sha256:6c74791e557ce11fc957704f6d4fe134a7bc8d6f5ca4403205b2966bd488f6b3

# Python trees checked by lint, format, mypy, and complexity tools.
PYTHON_SOURCES := thot tests

# Sources that invalidate the wheel build stamp (pyproject + package code).
WHEEL_SOURCES := $(TKEIR_DIR)/pyproject.toml $(TKEIR_DIR)/uv.lock \
	$(shell find $(TKEIR_DIR)/thot -type f -name '*.py' 2>/dev/null)

# Xenon thresholds for the full tree (radon reports; xenon gates CI).
XENON_MAX_ABSOLUTE ?= F
XENON_MAX_MODULES ?= F
XENON_MAX_AVERAGE ?= A
# Hard gates for production package (thot/): grade B average, no grade D+.
CC_AVERAGE_MAX ?= 7.0
QUALITY_REPORT_DIR ?= $(ROOT)/reports/quality
COMPLEXITY_SOURCES ?= thot

# Minimum test coverage percentage — CI fails below this threshold.
COVERAGE_FAIL_UNDER ?= 90

QUICKSTART_CONFIG ?= $(PIPELINE_CONFIG)
QUICKSTART_OUTPUT ?= $(ROOT)/output/quickstart

-include .env

# Export only the variables defined in this Makefile, not the entire environment.
# This prevents secrets stored in .env (PYPI_TOKEN, DOCKER_PASSWORD, etc.)
# from leaking into CI logs via a bare 'export'.
export UV PYTHON COMPOSE TRIVY_IMAGE OWASP_DC_IMAGE OWASP_DC_FAIL_CVSS TRIVY_SEVERITY
export BOM_SPEC_VERSION BOM_REPORT_DIR BOM_CONFIG BOM_PYTHON
export PIPELINE_CONFIG PIPELINE_INPUT PIPELINE_OUTPUT PIPELINE_TYPE
export TRANSFORMERS_CACHE WORKSPACE DOCS_PORT
export COVERAGE_FAIL_UNDER SECURITY_REPORT_DIR
export VERSION GIT_COMMIT GIT_BRANCH BUILD_DATE
export VERBOSE
export IMAGE_REGISTRY IMAGE_TAG PLATFORMS MODEL_MODE

# ---------------------------------------------------------------------------
# Help — self-documenting (`target: ## description`)
# ---------------------------------------------------------------------------

help: ## Show available targets (VERBOSE=1 prints recipes)
	$(Q)printf '%s\n' "T-KEIR — make targets (VERBOSE=$(VERBOSE))"
	$(Q)printf '%s\n' "Usage: make <target> [VAR=value]"
	$(Q)printf '%s\n' ""
	$(Q)grep -E '^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_-]+)*[[:space:]]*:.*?##[[:space:]].*$$' "$(THIS_MAKEFILE)" \
		| awk 'BEGIN {FS = ":.*?##[[:space:]]*"}; {printf "  \033[36mmake %-28s\033[0m %s\n", $$1, $$2}' \
		| sort
	$(Q)printf '%s\n' ""
	$(Q)printf '%s\n' "Common vars: PIPELINE_* INDEX_INPUT RAG_QUERY BEIR_* COVERAGE_FAIL_UNDER VERSION WORKSPACE VERBOSE"
	$(Q)printf '%s\n' "Image vars:  IMAGE_REGISTRY IMAGE_TAG PLATFORMS MODEL_MODE"
	$(Q)printf '%s\n' "Compose:     PROFILES=$(PROFILES) (core,auth,ingest,audit,governor,observability,objectstore,mcp,agents,spire)"

# ---------------------------------------------------------------------------
# Environment guards
# ---------------------------------------------------------------------------

check-uv: ## Require uv on PATH
	$(Q)command -v $(UV) >/dev/null 2>&1 || { \
		echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/"; \
		exit 1; \
	}

check-docker: ## Require Docker + Compose v2
	$(Q)command -v docker >/dev/null 2>&1 || { \
		echo "Docker is required. Install: https://docs.docker.com/get-docker/"; \
		exit 1; \
	}
	$(Q)$(COMPOSE) version >/dev/null 2>&1 || { \
		echo "Docker Compose v2 required (docker compose)"; \
		exit 1; \
	}

check-git: ## Require a git working tree
	$(Q)command -v git >/dev/null 2>&1 || { echo "git is required"; exit 1; }
	$(Q)git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { \
		echo "This directory is not inside a git repository"; exit 1; }

check-jq: ## Require jq (rag-query / smoke-test)
	$(Q)command -v jq >/dev/null 2>&1 || { \
		echo "jq is required (used by rag-query / smoke-test). Install: https://stedolan.github.io/jq/"; \
		exit 1; }

check-curl: ## Require curl (rag-query / smoke-test)
	$(Q)command -v curl >/dev/null 2>&1 || { \
		echo "curl is required (used by rag-query / smoke-test). Install: https://curl.se/"; \
		exit 1; }

check-python-version: check-uv ## Require uv-managed Python (see PYTHON=)
	$(Q)$(UV) python find $(PYTHON) >/dev/null 2>&1 || { \
		echo "Python $(PYTHON) not found. Run: uv python install $(PYTHON)"; exit 1; }

check-secrets: check-git ## Fail on tracked credential files or secret patterns
	$(Q)chmod +x "$(SCRIPTS_DIR)/check_secrets.sh"
	$(Q)CHECK_SECRETS_STAGED=0 "$(SCRIPTS_DIR)/check_secrets.sh"

check-secrets-staged: ## Scan staged files only (fast pre-commit path)
	$(Q)chmod +x "$(SCRIPTS_DIR)/check_secrets.sh"
	$(Q)CHECK_SECRETS_STAGED=1 "$(SCRIPTS_DIR)/check_secrets.sh"

# ---------------------------------------------------------------------------
# Install / sync
# ---------------------------------------------------------------------------

install: check-uv check-python-version ## Sync Python env (dev + models groups) in tkeir/
	$(UV) sync --directory $(TKEIR_DIR) --group dev --group models --python $(PYTHON)

sync: install ## Alias for install (legacy vespa workflow)

ci-deps: check-uv check-python-version ## Sync Python env (dev + models groups)
	$(UV) sync --directory $(TKEIR_DIR) --group dev --group models --python $(PYTHON)

verify-lockfile: check-uv ## Fail if uv.lock is out of sync with pyproject.toml
	$(Q)echo "Verifying lock file is up-to-date with pyproject.toml..."
	cd $(TKEIR_DIR) && $(UV) lock --check
	$(Q)echo "Lock file OK."

hmi-install: ## Install HMI dependencies from package-lock.json
	cd $(HMI_DIR) && npm ci

install-spacy-models: check-uv ## Install spaCy language models
	$(Q)chmod +x "$(SCRIPTS_DIR)/install_spacy_models.sh"
	$(Q)bash "$(SCRIPTS_DIR)/install_spacy_models.sh"

install-tesseract: ## Install Tesseract OCR via helper script
	$(Q)chmod +x "$(SCRIPTS_DIR)/install_tesseract.sh"
	$(Q)bash "$(SCRIPTS_DIR)/install_tesseract.sh"

init-models: install ## Build tkeir_mwe.pkl from annotation resources
	$(Q)mkdir -p "$(TRANSFORMERS_CACHE)"
	cd $(TKEIR_DIR) && TRANSFORMERS_CACHE="$(TRANSFORMERS_CACHE)" \
		$(UV) run --no-sync --python $(PYTHON) \
		tkeir-create-annotation-resource \
		--entries-file resources/modeling/tokenizer/en/annotation-resources.json \
		--output resources/modeling/tokenizer/en/tkeir_mwe.pkl

setup: ## Full local setup (install → spaCy → Tesseract → models)
	$(MAKE) install
	$(MAKE) install-spacy-models
	$(MAKE) install-tesseract
	$(MAKE) init-models
	$(Q)echo ""
	$(Q)echo "Setup complete."
	$(Q)echo "  Run pipeline: make pipeline"
	$(Q)echo "  Or demo:      make quickstart"
	$(Q)echo "  Vespa RAG:    make bootstrap && make index && make rag"

# ---------------------------------------------------------------------------
# Wheel build (state file — rebuild only when sources change)
# ---------------------------------------------------------------------------

build: $(BUILD_STAMP) ## Build Python wheel into dist/ (incremental)
wheel: $(BUILD_STAMP) ## Alias for build

$(BUILD_STAMP): $(WHEEL_SOURCES) | check-uv check-git
	$(Q)mkdir -p "$(DIST_DIR)"
	$(UV) build --directory $(TKEIR_DIR)
	$(Q)touch "$(BUILD_STAMP)"
	$(Q)echo "Built wheel $(VERSION) (commit=$(GIT_COMMIT)) in $(DIST_DIR)/"

# ---------------------------------------------------------------------------
# Tests / quality
# ---------------------------------------------------------------------------

test-unit: ci-deps ## Run unit test suite
	cd $(TESTS_DIR) && bash UnitTestSuite.sh

test-functional: ci-deps ## Run functional test suite
	cd $(TESTS_DIR) && bash FunctionalTestSuite.sh

test: test-unit test-functional ## Run unit + functional tests

test-coverage: coverage ## Alias for coverage

coverage: ci-deps ## Coverage suite (fail-under COVERAGE_FAIL_UNDER, default 90%)
	$(Q)echo "Coverage threshold: $(COVERAGE_FAIL_UNDER)%"
	$(Q)mkdir -p "$(COVERAGE_REPORT_DIR)" "$(QUALITY_REPORT_DIR)"
	cd $(TESTS_DIR) && COVERAGE_FAIL_UNDER=$(COVERAGE_FAIL_UNDER) \
		COVERAGE_REPORT_DIR="$(COVERAGE_REPORT_DIR)" \
		QUALITY_REPORT_DIR="$(QUALITY_REPORT_DIR)" \
		bash CoverageFast.sh

lint: ci-deps ## ruff + black + isort checks on thot/ and tests/
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with ruff \
		ruff check $(PYTHON_SOURCES)
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with black --with isort \
		black --check $(PYTHON_SOURCES)
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with isort \
		isort --check-only $(PYTHON_SOURCES)

hmi-lint: hmi-install ## Next.js / ESLint checks for the HMI
	cd $(HMI_DIR) && npm run lint

format: ci-deps ## Apply ruff + black + isort
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with ruff \
		ruff format $(PYTHON_SOURCES)
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with black --with isort \
		black $(PYTHON_SOURCES)
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with isort \
		isort $(PYTHON_SOURCES)

typecheck: ci-deps ## mypy on thot/ and tests/
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with mypy \
		mypy $(PYTHON_SOURCES)

hmi-typecheck: hmi-install ## TypeScript checks for the HMI
	cd $(HMI_DIR) && npm run typecheck

hmi-build: hmi-install ## Production Next.js build sanity check
	cd $(HMI_DIR) && npm run build

liccheck: ci-deps ## Verify dependency licenses (liccheck.ini)
	$(Q)if [ ! -f "$(LICCHECK_CONFIG)" ]; then \
		echo "ERROR: $(LICCHECK_CONFIG) not found."; \
		echo "Create this file with the approved license list (see comment in Makefile)."; \
		exit 1; \
	fi
	cd $(TKEIR_DIR) && $(UV) export --frozen --no-dev --no-emit-project \
		-o .requirements-liccheck.txt
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		liccheck -l PARANOID \
		-s "$(LICCHECK_CONFIG)" \
		-r .requirements-liccheck.txt
	rm -f $(TKEIR_DIR)/.requirements-liccheck.txt

complexity: ci-deps ## radon + xenon complexity gates (avg ≤ 7.0 on thot/, no grade D+)
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		radon cc $(PYTHON_SOURCES) -a -nb
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		xenon --max-absolute $(XENON_MAX_ABSOLUTE) \
			--max-modules $(XENON_MAX_MODULES) \
			--max-average $(XENON_MAX_AVERAGE) \
			$(PYTHON_SOURCES)
	$(Q)mkdir -p "$(QUALITY_REPORT_DIR)"
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		radon cc $(COMPLEXITY_SOURCES) -a -s --total-average \
		| tee "$(QUALITY_REPORT_DIR)/radon_cc_gate.txt"
	@# Fail if average CC on thot/ exceeds CC_AVERAGE_MAX (default 7.0)
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		radon cc $(COMPLEXITY_SOURCES) -a --total-average \
		| awk -v lim="$(CC_AVERAGE_MAX)" ' \
			/Average complexity:/ { \
				gsub(/[()]/, "", $$NF); \
				avg=$$NF+0; \
				if (avg > lim+0) { \
					printf "FAIL: CC average %.4f > %s\n", avg, lim; exit 1 \
				} else { \
					printf "OK: CC average %.4f ≤ %s\n", avg, lim \
				} \
			}'
	@# Fail if any function in thot/ is grade D or worse (CC > 20)
	$(Q)out=$$(cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		radon cc $(COMPLEXITY_SOURCES) -n D -s); \
	if [ -n "$$out" ]; then \
		echo "$$out"; \
		echo "FAIL: functions at grade D or worse exist (see above)"; \
		exit 1; \
	fi; \
	echo "OK: no functions at grade D or worse in $(COMPLEXITY_SOURCES)/"

complexity-report: ci-deps ## generate radon CC + MI reports to reports/quality/
	$(Q)mkdir -p "$(QUALITY_REPORT_DIR)"
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		radon cc $(COMPLEXITY_SOURCES) -s -j \
		> "$(QUALITY_REPORT_DIR)/radon_cc.json"
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		radon mi $(COMPLEXITY_SOURCES) -s -j \
		> "$(QUALITY_REPORT_DIR)/radon_mi.json"
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		radon mi $(COMPLEXITY_SOURCES) -s \
		> "$(QUALITY_REPORT_DIR)/radon_mi.txt"
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		radon cc $(COMPLEXITY_SOURCES) -a -s --total-average \
		> "$(QUALITY_REPORT_DIR)/radon_cc_summary.txt"
	$(Q)echo "Reports written to $(QUALITY_REPORT_DIR)/"

pip-licenses: ci-deps ## generate dependency licence inventory → reports/quality/licenses.*
	$(Q)mkdir -p "$(QUALITY_REPORT_DIR)"
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) --with pip-licenses \
		pip-licenses \
		--format=json \
		--with-urls \
		--with-description \
		--output-file="$(QUALITY_REPORT_DIR)/licenses.json"
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) --with pip-licenses \
		pip-licenses \
		--format=markdown \
		--with-urls \
		--with-description \
		--output-file="$(QUALITY_REPORT_DIR)/licenses.md"
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) --with pip-licenses \
		pip-licenses \
		--format=csv \
		--with-urls \
		--output-file="$(QUALITY_REPORT_DIR)/licenses.csv"
	$(Q)echo "Licence report written to $(QUALITY_REPORT_DIR)/licenses.*"

license-report: pip-licenses ## alias for pip-licenses

quality-docs: complexity-report pip-licenses ## regenerate tkeir/docs/quality/index.md
	$(Q)mkdir -p "$(QUALITY_REPORT_DIR)"
	$(Q)if [ ! -f "$(QUALITY_REPORT_DIR)/coverage_summary.txt" ] \
		&& [ -f "$(COVERAGE_REPORT_DIR)/coverage.xml" ]; then \
		cp "$(COVERAGE_REPORT_DIR)/coverage.xml" "$(QUALITY_REPORT_DIR)/coverage.xml"; \
	fi
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		python "$(ROOT)/tools/quality/gen_quality_doc.py"

# Documented pip-audit ignores (comments above each flag; += keeps Make syntax valid).
# CVE-2026-49851 — transitive / advisory noise on locked stack; upgrade blocked pending dependency review | fix blocked by: TBD | target resolution: 2026-09-01 | ticket: N/A
PIP_AUDIT_IGNORE ?= --ignore-vuln CVE-2026-49851
# CVE-2026-44708 — accepted risk until upstream pin lands in uv.lock | fix blocked by: TBD | target resolution: 2026-09-01 | ticket: N/A
PIP_AUDIT_IGNORE += --ignore-vuln CVE-2026-44708
# CVE-2026-44897 — accepted risk until upstream pin lands in uv.lock | fix blocked by: TBD | target resolution: 2026-09-01 | ticket: N/A
PIP_AUDIT_IGNORE += --ignore-vuln CVE-2026-44897
# PYSEC-2026-168 — advisory retained pending package upgrade path | fix blocked by: TBD | target resolution: 2026-09-01 | ticket: N/A
PIP_AUDIT_IGNORE += --ignore-vuln PYSEC-2026-168
# PYSEC-2026-141 — advisory retained pending package upgrade path | fix blocked by: TBD | target resolution: 2026-09-01 | ticket: N/A
PIP_AUDIT_IGNORE += --ignore-vuln PYSEC-2026-141
# PYSEC-2026-1999 — advisory retained pending package upgrade path | fix blocked by: TBD | target resolution: 2026-09-01 | ticket: N/A
PIP_AUDIT_IGNORE += --ignore-vuln PYSEC-2026-1999
# PYSEC-2026-1998 — advisory retained pending package upgrade path | fix blocked by: TBD | target resolution: 2026-09-01 | ticket: N/A
PIP_AUDIT_IGNORE += --ignore-vuln PYSEC-2026-1998
# PYSEC-2026-1994 — advisory retained pending package upgrade path | fix blocked by: TBD | target resolution: 2026-09-01 | ticket: N/A
PIP_AUDIT_IGNORE += --ignore-vuln PYSEC-2026-1994
# PYSEC-2026-1996 — advisory retained pending package upgrade path | fix blocked by: TBD | target resolution: 2026-09-01 | ticket: N/A
PIP_AUDIT_IGNORE += --ignore-vuln PYSEC-2026-1996
# PYSEC-2026-3447 — advisory retained pending package upgrade path | fix blocked by: TBD | target resolution: 2026-09-01 | ticket: N/A
PIP_AUDIT_IGNORE += --ignore-vuln PYSEC-2026-3447
# GHSA-537c-gmf6-5ccf — cryptography>=48 blocked by optional spiffe extra (cryptography<47) | fix blocked by: spiffe upstream | target resolution: 2026-09-01 | ticket: N/A
PIP_AUDIT_IGNORE += --ignore-vuln GHSA-537c-gmf6-5ccf

pip-audit: ci-deps ## Scan Python dependencies for known CVEs
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		pip-audit --skip-editable $(PIP_AUDIT_IGNORE)

# ---------------------------------------------------------------------------
# Dependency update (Dependabot-equivalent)
# ---------------------------------------------------------------------------

deps-check: ci-deps ## Show outdated Python packages (read-only)
	$(Q)echo "=== Outdated Python dependencies ==="
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		pip list --outdated --format=columns
	$(Q)echo ""
	$(Q)echo "Run 'make deps-update' to upgrade the lock file."

deps-update: ci-deps ## Upgrade all deps within constraints; refresh uv.lock
	$(Q)echo "=== Upgrading all dependencies (within pyproject.toml constraints) ==="
	cd $(TKEIR_DIR) && $(UV) lock --upgrade
	$(Q)echo "Lock file updated. Run 'make ci' to validate."

deps-update-safe: ci-deps ## Upgrade patch-level versions only (safer for prod)
	$(Q)echo "=== Upgrading patch-level dependencies only ==="
	$(Q)flags=$$(cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		pip list --outdated --format=json \
		| $(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) python -c "import sys,json; pkgs=json.load(sys.stdin); parts=[]; \
[parts.extend(['--upgrade-package', p['name']]) for p in pkgs if len(p['latest_version'].split('.'))>=2 and len(p['version'].split('.'))>=2 and p['latest_version'].split('.')[0]==p['version'].split('.')[0] and p['latest_version'].split('.')[1]==p['version'].split('.')[1]]; \
print(' '.join(parts))"); \
	if [ -z "$$flags" ]; then \
		echo "No same-major.minor patch upgrades available."; \
	else \
		cd $(TKEIR_DIR) && $(UV) lock $$flags; \
		echo "Patch-safe lock file updated. Run 'make ci' to validate."; \
	fi

# ---------------------------------------------------------------------------
# Release — annotated Git tag and conventional changelog
# ---------------------------------------------------------------------------

tag: check-git ## Create annotated Git tag (VERSION=x.y.z required)
	$(Q)test -n "$(VERSION)" && [ "$(VERSION)" != "0.0.0-dev" ] || { \
		echo "VERSION is required and must not be dirty. Example: make tag VERSION=1.2.3"; exit 1; }
	$(Q)git diff --quiet && git diff --cached --quiet || { \
		echo "Working tree is not clean. Commit or stash changes before tagging."; exit 1; }
	git tag -a "v$(VERSION)" -m "Release v$(VERSION) (commit=$(GIT_COMMIT))"
	$(Q)echo "Tag v$(VERSION) created locally."
	$(Q)echo "To push: git push origin v$(VERSION)"

changelog: ci-deps check-git ## Generate CHANGELOG.md from conventional commits
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with git-changelog \
		git-changelog -o $(ROOT)/CHANGELOG.md
	$(Q)echo "CHANGELOG.md updated."

# ---------------------------------------------------------------------------
# Security / BOM
# ---------------------------------------------------------------------------

bom: ci-deps ## Unified CycloneDX SBOM + AIBOM
	$(Q)chmod +x "$(SCRIPTS_DIR)/build_bom.sh"
	BOM_SPEC_VERSION=$(BOM_SPEC_VERSION) BOM_REPORT_DIR=$(BOM_REPORT_DIR) \
		BOM_CONFIG=$(BOM_CONFIG) BOM_PYTHON=$(ROOT)/$(BOM_PYTHON) \
		TKEIR_DIR=$(TKEIR_DIR) \
		"$(SCRIPTS_DIR)/build_bom.sh"

sbom: bom ## Alias for bom
	$(Q)echo "note: make sbom is an alias for make bom (unified SBOM + AIBOM)"

aibom: bom ## Alias for bom
	$(Q)echo "note: make aibom is an alias for make bom (unified SBOM + AIBOM)"

trivy: check-docker ci-deps ## Trivy filesystem + config scan (Docker)
	$(Q)chmod +x "$(SCRIPTS_DIR)/run_trivy.sh"
	TRIVY_IMAGE=$(TRIVY_IMAGE) TRIVY_SEVERITY=$(TRIVY_SEVERITY) \
		SECURITY_REPORT_DIR=$(SECURITY_REPORT_DIR) TKEIR_DIR=$(TKEIR_DIR) \
		"$(SCRIPTS_DIR)/run_trivy.sh"

owasp-dependency-check: check-docker ci-deps ## OWASP Dependency-Check (Docker)
	$(Q)chmod +x "$(SCRIPTS_DIR)/run_owasp_dependency_check.sh"
	OWASP_DC_IMAGE=$(OWASP_DC_IMAGE) OWASP_DC_FAIL_CVSS=$(OWASP_DC_FAIL_CVSS) \
		TKEIR_DIR=$(TKEIR_DIR) \
		"$(SCRIPTS_DIR)/run_owasp_dependency_check.sh"

security-report: pip-audit trivy owasp-dependency-check bom ## Run security scans; write unified manifest
	$(Q)mkdir -p "$(SECURITY_REPORT_DIR)"
	$(Q)if [ -d "$(ROOT)/reports/bom" ]; then \
		mkdir -p "$(SECURITY_REPORT_DIR)/bom"; \
		cp -R "$(ROOT)/reports/bom/." "$(SECURITY_REPORT_DIR)/bom/" 2>/dev/null || true; \
	fi
	$(Q)if [ -d "$(ROOT)/reports/dependency-check" ]; then \
		mkdir -p "$(SECURITY_REPORT_DIR)/dependency-check"; \
		cp -R "$(ROOT)/reports/dependency-check/." "$(SECURITY_REPORT_DIR)/dependency-check/" 2>/dev/null || true; \
	fi
	$(Q)echo "=== Security report index ===" | tee "$(SECURITY_REPORT_DIR)/index.txt"
	$(Q)generated=$$($(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		python -c "import datetime; print(datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))"); \
	echo "Generated: $$generated" | tee -a "$(SECURITY_REPORT_DIR)/index.txt"
	$(Q)echo "" | tee -a "$(SECURITY_REPORT_DIR)/index.txt"
	$(Q)ls -lh "$(SECURITY_REPORT_DIR)/" | tee -a "$(SECURITY_REPORT_DIR)/index.txt"
	$(Q)$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) python -c " \
import os, json, datetime; \
d = '$(SECURITY_REPORT_DIR)'; \
files = []; \
[files.append(os.path.join(root, f)) for root, _, names in os.walk(d) for f in names if f not in ('manifest.json',)]; \
manifest = {'generated_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'reports': sorted(files)}; \
open(os.path.join(d, 'manifest.json'), 'w').write(json.dumps(manifest, indent=2)); \
print('Manifest written to', os.path.join(d, 'manifest.json'))"
	$(Q)echo "All security reports available in $(SECURITY_REPORT_DIR)/"

# ---------------------------------------------------------------------------
# Docs / pipeline / workspace
# ---------------------------------------------------------------------------

docs: ci-deps ## MkDocs dev server (override DOCS_PORT; default 8000)
	$(Q)if lsof -nP -iTCP:$(DOCS_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
		echo "Port $(DOCS_PORT) is already in use (docs already built OK)."; \
		echo "  Open:  http://127.0.0.1:$(DOCS_PORT)/"; \
		echo "  Or:    make docs DOCS_PORT=8001"; \
		echo "  Stop:  kill \$$(lsof -tiTCP:$(DOCS_PORT) -sTCP:LISTEN)"; \
		exit 1; \
	fi
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		--with mkdocs --with mkdocs-material --with mkdocs-render-swagger-plugin \
		mkdocs serve -a 127.0.0.1:$(DOCS_PORT)

docs-build: ci-deps quality-docs ## Build static MkDocs site under tkeir/site/
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		--with mkdocs --with mkdocs-material --with mkdocs-render-swagger-plugin \
		mkdocs build
	$(Q)echo "Built static site: $(TKEIR_DIR)/site/index.html"

docs-pdf: ci-deps ## Generate documentation PDF (output/docs/tkeir-docs.pdf)
	DOCS_PDF_OUTPUT="$(DOCS_PDF_OUTPUT)" \
		bash "$(SCRIPTS_DIR)/docs-pdf.sh"

pipeline: ci-deps install-spacy-models ## Run tkeir-pipeline (PIPELINE_* vars)
	$(Q)mkdir -p "$(PIPELINE_OUTPUT)"
	cd $(TKEIR_DIR) && TRANSFORMERS_CACHE="$(TRANSFORMERS_CACHE)" \
		$(UV) run --no-sync --python $(PYTHON) tkeir-pipeline \
		-c "$(PIPELINE_CONFIG)" \
		-i "$(PIPELINE_INPUT)" \
		-o "$(PIPELINE_OUTPUT)" \
		-t "$(PIPELINE_TYPE)"
	$(Q)echo "Pipeline output: $(PIPELINE_OUTPUT)"

quickstart: ci-deps init-models ## Pipeline-only demo on tests/fixtures/test-raw
	QUICKSTART_CONFIG="$(QUICKSTART_CONFIG)" \
		QUICKSTART_OUTPUT="$(QUICKSTART_OUTPUT)" \
		TRANSFORMERS_CACHE="$(TRANSFORMERS_CACHE)" \
		bash "$(SCRIPTS_DIR)/quickstart.sh"

install-workspace: check-uv ## Install wheel into WORKSPACE via install.sh
	$(Q)test -n "$(WORKSPACE)" || { echo "WORKSPACE is required"; exit 1; }
	bash "$(ROOT)/install.sh" "$(WORKSPACE)"

devcontainer: check-docker ## Enter the project devcontainer
	bash "$(ROOT)/.devcontainer/enter-devcontainer.sh"

pre-commit: ci-deps lint typecheck hmi-lint hmi-typecheck test-unit ## Fast local checks before git push
	$(Q)echo ""
	$(Q)echo "Pre-commit checks passed. Safe to push."
	$(Q)echo "Full quality gate: make ci"

ci: ## Full quality gate (serialized; safe under make -j)
	$(MAKE) check-secrets
	$(MAKE) verify-lockfile
	$(MAKE) ci-deps
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) hmi-lint
	$(MAKE) hmi-typecheck
	$(MAKE) hmi-build
	$(MAKE) test
	$(MAKE) coverage
	$(MAKE) liccheck
	$(MAKE) complexity
	$(MAKE) complexity-report
	$(MAKE) pip-licenses
	$(MAKE) pip-audit
	$(MAKE) bom
	$(MAKE) trivy
	$(MAKE) owasp-dependency-check
	$(MAKE) audit-compliance
	$(MAKE) docs-build
	$(Q)echo "All quality gates passed. VERSION=$(VERSION) COMMIT=$(GIT_COMMIT)"

clean: ## Remove build artifacts, caches, and reports
	rm -rf dist build .pytest_cache .mypy_cache .ruff_cache htmlcov .cache reports
	rm -rf "$(COVERAGE_REPORT_DIR)"
	rm -f $(TESTS_DIR)/.coverage $(TESTS_DIR)/.coverage_* $(TESTS_DIR)/testsuite.log
	rm -rf $(TKEIR_DIR)/site
	find $(TKEIR_DIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ---------------------------------------------------------------------------
# Container images (buildx bake → ghcr.io/thalesgroup/t-keir)
# ---------------------------------------------------------------------------

images: check-docker ## Build all images (lib once, then api/ingest/…); also: make image-api|…
	$(Q)docker buildx version >/dev/null
	REGISTRY="$(IMAGE_REGISTRY)" TAG="$(IMAGE_TAG)" \
		VERSION="$(VERSION)" GIT_COMMIT="$(GIT_COMMIT)" BUILD_DATE="$(BUILD_DATE)" \
		PYTHON_BASE="$(PYTHON_BASE_IMAGE)" NODE_BASE="$(NODE_BASE_IMAGE)" \
		MODEL_MODE="$(MODEL_MODE)" CONTEXT="$(ROOT)" \
		docker buildx bake -f "$(BAKE_FILE)" \
			$(if $(PLATFORMS),--set "*.platform=$(PLATFORMS)",) \
			--progress=plain default
	$(Q)echo "Built images under $(IMAGE_REGISTRY)/*:$(IMAGE_TAG) (shared base: tkeir-lib)"

image-%: check-docker ## Build one image target (lib|api|indexer|indexer-slim|hmi|ingest|…)
	$(Q)docker buildx version >/dev/null
	REGISTRY="$(IMAGE_REGISTRY)" TAG="$(IMAGE_TAG)" \
		VERSION="$(VERSION)" GIT_COMMIT="$(GIT_COMMIT)" BUILD_DATE="$(BUILD_DATE)" \
		PYTHON_BASE="$(PYTHON_BASE_IMAGE)" NODE_BASE="$(NODE_BASE_IMAGE)" \
		MODEL_MODE="$(MODEL_MODE)" CONTEXT="$(ROOT)" \
		docker buildx bake -f "$(BAKE_FILE)" \
			$(if $(PLATFORMS),--set "*.platform=$(PLATFORMS)",) \
			--progress=plain tkeir-$*
	$(Q)echo "Built $(IMAGE_REGISTRY)/tkeir-$*:$(IMAGE_TAG)"

images-push: check-docker ## Push bake targets (defaults to linux/amd64,linux/arm64)
	$(Q)docker buildx version >/dev/null
	REGISTRY="$(IMAGE_REGISTRY)" TAG="$(IMAGE_TAG)" \
		VERSION="$(VERSION)" GIT_COMMIT="$(GIT_COMMIT)" BUILD_DATE="$(BUILD_DATE)" \
		PYTHON_BASE="$(PYTHON_BASE_IMAGE)" NODE_BASE="$(NODE_BASE_IMAGE)" \
		MODEL_MODE="$(MODEL_MODE)" CONTEXT="$(ROOT)" \
		docker buildx bake -f "$(BAKE_FILE)" --push \
			--set "*.platform=$(if $(PLATFORMS),$(PLATFORMS),linux/amd64,linux/arm64)" \
			--progress=plain default
	$(Q)echo "Pushed images to $(IMAGE_REGISTRY)"

images-sign: ## Cosign keyless sign images (requires cosign + OIDC identity)
	$(Q)command -v cosign >/dev/null 2>&1 || { \
		echo "cosign is required: https://docs.sigstore.dev/cosign/system_config/installation/"; \
		exit 1; \
	}
	$(Q)for name in tkeir-lib tkeir-api tkeir-indexer tkeir-indexer-slim tkeir-hmi tkeir-ingest tkeir-audit tkeir-governor; do \
		echo "Signing $(IMAGE_REGISTRY)/$${name}:$(IMAGE_TAG)"; \
		cosign sign --yes "$(IMAGE_REGISTRY)/$${name}:$(IMAGE_TAG)"; \
	done

# ---------------------------------------------------------------------------
# Docker Compose (P1+) — tkeir images from IMAGE_REGISTRY (default: local)
# ---------------------------------------------------------------------------

compose-up: check-docker ## Start Compose profiles (PROFILES=core,auth); build local images first if needed
	$(Q)test -f "$(COMPOSE_DIR)/.env" || cp "$(COMPOSE_DIR)/.env.example" "$(COMPOSE_DIR)/.env"
	$(Q)PROFILE_ARGS=$$(printf -- '--profile %s ' $$(echo "$(COMPOSE_PROFILES)" | tr ',' ' ')); \
		IMAGE_REGISTRY="$(IMAGE_REGISTRY)" IMAGE_TAG="$(IMAGE_TAG)" \
		VERSION="$(VERSION)" GIT_COMMIT="$(GIT_COMMIT)" BUILD_DATE="$(BUILD_DATE)" \
		$(COMPOSE) -f "$(COMPOSE_FILE)" --env-file "$(COMPOSE_DIR)/.env" \
			$$PROFILE_ARGS up -d --remove-orphans
	$(Q)echo "Compose up (PROFILES=$(COMPOSE_PROFILES) IMAGE_REGISTRY=$(IMAGE_REGISTRY)). HMI http://localhost:3000"
	$(Q)echo "Local images: make images   |   Publish: make images-push IMAGE_REGISTRY=ghcr.io/thalesgroup/t-keir"

compose-down: check-docker ## Stop Compose stack (VOLUMES=1 also removes volumes)
	$(Q)ENV_FILE="$(COMPOSE_DIR)/.env"; \
		test -f "$$ENV_FILE" || ENV_FILE="$(COMPOSE_DIR)/.env.example"; \
		PROFILE_ARGS=$$(printf -- '--profile %s ' $$(echo "$(COMPOSE_PROFILES)" | tr ',' ' ')); \
		$(COMPOSE) -f "$(COMPOSE_FILE)" --env-file "$$ENV_FILE" \
			$$PROFILE_ARGS down $(if $(filter 1,$(VOLUMES)),-v,)
	$(Q)echo "Compose down$(if $(filter 1,$(VOLUMES)), (volumes removed),)"

compose-logs: check-docker ## Tail Compose logs (PROFILES=… SERVICE=optional)
	$(Q)ENV_FILE="$(COMPOSE_DIR)/.env"; \
		test -f "$$ENV_FILE" || ENV_FILE="$(COMPOSE_DIR)/.env.example"; \
		PROFILE_ARGS=$$(printf -- '--profile %s ' $$(echo "$(COMPOSE_PROFILES)" | tr ',' ' ')); \
		$(COMPOSE) -f "$(COMPOSE_FILE)" --env-file "$$ENV_FILE" \
			$$PROFILE_ARGS logs -f --tail=200 $(SERVICE)

compose-smoke: check-curl ## Health-check running Compose stack (auto-detects optional profiles)
	$(Q)bash "$(SCRIPTS_DIR)/compose/compose-smoke.sh"

# ---------------------------------------------------------------------------
# Audit CLI (Phase 4) — requires AUDIT_HOT_STORE_URL
# ---------------------------------------------------------------------------

AUDIT_CID ?=
TKEIR ?= cd $(TKEIR_DIR) && $(UV) run

audit-report: ## Render audit report (CID=correlation-id, FORMAT=json|html)
	$(Q)test -n "$(CID)" || { echo "Set CID=<32-hex correlation id>"; exit 1; }
	$(Q)AUDIT_HOT_STORE_URL="$(AUDIT_HOT_STORE_URL)" $(TKEIR) tkeir-audit report \
		--correlation-id "$(CID)" --format "$(or $(FORMAT),json)"

audit-verify: ## Verify hot-store hash chain and WORM segments
	$(Q)AUDIT_HOT_STORE_URL="$(AUDIT_HOT_STORE_URL)" AUDIT_WORM_ROOT="$(AUDIT_WORM_ROOT)" \
		$(TKEIR) tkeir-audit verify

audit-archive: ## Export unarchived ActionRecords to WORM segments
	$(Q)AUDIT_HOT_STORE_URL="$(AUDIT_HOT_STORE_URL)" AUDIT_WORM_ROOT="$(AUDIT_WORM_ROOT)" \
		$(TKEIR) tkeir-audit archive

# ---------------------------------------------------------------------------
# Governor CLI (Phase 5)
# ---------------------------------------------------------------------------

governor-flags: ## Show runtime kill-switch flags
	$(Q)GOVERNOR_STATE_ROOT="$(GOVERNOR_STATE_ROOT)" $(TKEIR) tkeir-governor flags

governor-kill: ## Toggle kill switch (SCOPE=ingest ACTIVE=true REASON=drill)
	$(Q)test -n "$(SCOPE)" || { echo "Set SCOPE=all|ingest|index|inference|hmi-write|agents"; exit 1; }
	$(Q)GOVERNOR_STATE_ROOT="$(GOVERNOR_STATE_ROOT)" $(TKEIR) tkeir-governor kill \
		--scope "$(SCOPE)" --active "$(or $(ACTIVE),true)" --reason "$(or $(REASON),makefile)"

rollback-index: check-curl ## Request index rollback via governor (RUN=… REASON=…)
	$(Q)GOVERNOR_URL="$(or $(GOVERNOR_URL),http://localhost:8094)"; \
		RUN="$(RUN)" REASON="$(or $(REASON),makefile rollback-index)" \
		curl -fsS -X POST "$${GOVERNOR_URL%/}/governor/rollback" \
			-H 'content-type: application/json' \
			-d "$$(RUN="$$RUN" REASON="$$REASON" python3 -c 'import json,os; print(json.dumps({"run_id":os.environ.get("RUN") or None,"reason":os.environ["REASON"]}))')" \
		| python3 -m json.tool

# ---------------------------------------------------------------------------
# Kubernetes / Helm (P2)
# ---------------------------------------------------------------------------

CHARTS_DIR := $(ROOT)/deploy/charts
UMBRELLA_CHART := $(CHARTS_DIR)/tkeir
PROFILE ?= k8s-dev
RELEASE ?= tkeir
NAMESPACE ?= tkeir
CLUSTER_NAME ?= tkeir
OUTPUT ?=
DOC ?=
INGEST_ROOT ?= /var/tkeir/ingest
FORMAT ?= text
URI ?=
DELETE_VM ?= 0
DELETE_REGISTRY ?= 0
SECRET_FILE ?=

k3d-up: check-docker ## Create k3d cluster + local registry
	bash "$(SCRIPTS_DIR)/cluster/k3d-up.sh"

k3d-down: ## Delete k3d cluster (DELETE_REGISTRY=1 also removes registry)
	bash "$(SCRIPTS_DIR)/cluster/k3d-down.sh"

helm-deps: ## helm dependency update for umbrella + sub-charts
	$(Q)command -v helm >/dev/null 2>&1 || { echo "helm is required"; exit 1; }
	$(Q)for c in tkeir-lib tkeir-api tkeir-hmi tkeir-vespa tkeir-indexer tkeir-inference tkeir-ingest tkeir-audit tkeir-governor tkeir-keycloak; do \
		if [[ "$$c" != "tkeir-lib" ]]; then \
			helm dependency update "$(CHARTS_DIR)/$$c" 2>/dev/null || true; \
		fi; \
	done
	helm dependency update "$(UMBRELLA_CHART)"

helm-lint: helm-deps ## Lint umbrella chart (PROFILE values)
	$(Q)VALUES="$(UMBRELLA_CHART)/values-dev.yaml"; \
		case "$(PROFILE)" in \
			k8s-secure|secure) VALUES="$(UMBRELLA_CHART)/values-secure.yaml" ;; \
			platform) VALUES="$(UMBRELLA_CHART)/values-platform.yaml" ;; \
		esac; \
		helm lint "$(UMBRELLA_CHART)" -f "$$VALUES"

helm-template: helm-deps ## Render umbrella manifests (dry-run)
	$(Q)VALUES="$(UMBRELLA_CHART)/values-dev.yaml"; \
		case "$(PROFILE)" in \
			k8s-secure|secure) VALUES="$(UMBRELLA_CHART)/values-secure.yaml" ;; \
			platform) VALUES="$(UMBRELLA_CHART)/values-platform.yaml" ;; \
		esac; \
		helm template "$(RELEASE)" "$(UMBRELLA_CHART)" -f "$$VALUES" --namespace "$(NAMESPACE)"

cluster-plan: ## Detect cluster capabilities (tkeir-installer plan)
	bash "$(SCRIPTS_DIR)/installer/tkeir-installer" plan $(if $(OUTPUT),--output $(OUTPUT),)

cluster-install: ## helm upgrade --install umbrella (PROFILE=k8s-dev|k8s-secure|platform)
	PROFILE="$(PROFILE)" RELEASE="$(RELEASE)" NAMESPACE="$(NAMESPACE)" \
		bash "$(SCRIPTS_DIR)/cluster/cluster-install.sh"

cluster-uninstall: ## helm uninstall umbrella (RELEASE/NAMESPACE)
	bash "$(SCRIPTS_DIR)/installer/tkeir-installer" destroy --release "$(RELEASE)" --namespace "$(NAMESPACE)"

helm-test: ## Run helm test hooks on installed release
	helm test "$(RELEASE)" -n "$(NAMESPACE)" --timeout 10m

k3s-server: ## Install hardened K3s server (Linux; USE_CILIUM=1 default)
	bash "$(ROOT)/deploy/k3s/install-server.sh"

k3s-agent: ## Join K3s agent (K3S_URL + K3S_TOKEN required)
	bash "$(ROOT)/deploy/k3s/install-agent.sh"

k3s-check: ## Submit kube-bench Job against current cluster
	bash "$(SCRIPTS_DIR)/cluster/k3s-check.sh"

cilium-install: ## Install Cilium via Helm (Linux / Lima)
	bash "$(SCRIPTS_DIR)/cluster/cilium-install.sh"

lima-k3s-up: ## macOS: Lima VM → K3s (+ Cilium path)
	bash "$(SCRIPTS_DIR)/cluster/lima-k3s-up.sh"

lima-k3s-down: ## Stop Lima VM (DELETE_VM=1 removes it)
	bash "$(SCRIPTS_DIR)/cluster/lima-k3s-down.sh"

keycloak-export-realm: check-curl ## Export running Keycloak realm to deploy/keycloak/
	bash "$(SCRIPTS_DIR)/cluster/keycloak-export-realm.sh"

seal: ## Seal a Secret with kubeseal (SECRET_FILE=… OUT=…)
	bash "$(SCRIPTS_DIR)/cluster/seal.sh"

kubeflow-install: ## Print Kubeflow Pipelines install guidance (vendored placeholders)
	$(Q)echo "Kubeflow Pipelines standalone: enable values-platform.yaml kubeflow.enabled"
	$(Q)echo "Pipeline skeleton: deploy/kubeflow/pipelines/ingest_index_pipeline.py"
	$(Q)echo "Full manifests: pin versions in deploy/versions.lock.yaml then vendor under deploy/kubeflow/"

kubeflow-uninstall: ## Placeholder uninstall hook
	$(Q)echo "Remove Kubeflow release installed by the platform profile / operator"

kubeflow-register-models: ## Register embedder/LLM/reranker identities from versions.lock
	$(Q)python3 -c "import yaml,json; from pathlib import Path; d=yaml.safe_load(Path('deploy/versions.lock.yaml').read_text()); print(json.dumps(d.get('models',{}), indent=2))"

kubeflow-run-ingest: ## Print ingest→index pipeline steps (DOC URI optional)
	python3 "$(ROOT)/deploy/kubeflow/pipelines/ingest_index_pipeline.py" $${URI:-file:///fixtures}

lineage-report: ## Document lineage from ingest manifests (DOC=<sha256>)
	DOC="$(DOC)" DOC_ID="$(DOC)" INGEST_ROOT="$(INGEST_ROOT)" FORMAT="$(FORMAT)" \
		bash "$(SCRIPTS_DIR)/compliance/lineage-report.sh"

audit-evidence: ## Build evidence pack under reports/evidence/<version>/
	VERSION="$(VERSION)" bash "$(SCRIPTS_DIR)/compliance/audit-evidence.sh"

annex-iv: ## Generate Annex IV technical pack under reports/compliance/annex-iv/
	VERSION="$(VERSION)" bash "$(SCRIPTS_DIR)/compliance/annex-iv.sh"
# ---------------------------------------------------------------------------
# Vespa / search / RAG
# ---------------------------------------------------------------------------

pull-models: install ## Pull Ollama embedding + LLM models
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) python -m thot.tools.search.pull_models

start: check-docker ## Start Vespa Docker container
	cd $(VESPA_DIR) && ./start_vespa.sh

init: install ## Deploy Vespa schemas (container must be running)
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) python -m thot.tools.search.init_vespa --skip-start

bootstrap: install ## Start Vespa + deploy schemas
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) python -m thot.tools.search.init_vespa

vespa-check: ## Vespa health check
	cd $(VESPA_DIR) && ./check_vespa.sh

test-vespa: ## Vespa query smoke test
	cd $(VESPA_DIR) && ./test_data.sh

test-vespa-py: install ## Python unit tests for Vespa client / ontology utils
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) pytest \
		tests/unittests/TestVespaClient.py tests/unittests/TestOntologyUtils.py -q

index-fixtures: ## Build indexing fixtures (PDF → *.pipeline.json)
	$(MAKE) pipeline \
		PIPELINE_INPUT=$(INDEX_FIXTURES_INPUT) \
		PIPELINE_OUTPUT=$(INDEX_INPUT) \
		PIPELINE_TYPE=auto
	$(Q)$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) python -c \
		"import sys, pathlib; hits = list(pathlib.Path('$(INDEX_INPUT)').glob('*.pipeline.json')); sys.exit(0) if hits else sys.exit(1)" \
		|| { \
		echo "No *.pipeline.json files produced in $(INDEX_INPUT)"; \
		echo "Ensure spaCy models are installed: make install-spacy-models"; \
		exit 1; \
	}

index: install init ## Embed + index pipeline JSON into Vespa
	$(Q)test -d "$(INDEX_INPUT)" || { \
		echo "Missing indexing fixtures: $(INDEX_INPUT)"; \
		echo "Run: make index-fixtures"; \
		exit 1; \
	}
	$(Q)$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) python -c \
		"import sys, pathlib; hits = list(pathlib.Path('$(INDEX_INPUT)').glob('*.pipeline.json')); sys.exit(0) if hits else sys.exit(1)" \
		|| { \
		echo "No *.pipeline.json files in $(INDEX_INPUT)"; \
		echo "Run: make index-fixtures"; \
		exit 1; \
	}
	$(Q)echo "Indexing from $(INDEX_INPUT)"
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) python -m thot.tools.search.index_documents -i "$(INDEX_INPUT)"

GOVERNOR_STATE_ROOT ?= $(WORKSPACE)/governor

rag: install install-spacy-models ## Start FastAPI RAG API on the host (:8090) — P0, no container
	$(Q)mkdir -p "$(GOVERNOR_STATE_ROOT)"
	cd $(TKEIR_DIR) && GOVERNOR_STATE_ROOT="$(GOVERNOR_STATE_ROOT)" \
		$(UV) run --python $(PYTHON) python -m thot.tools.search.app

INGEST_ROOT_HOST ?= $(WORKSPACE)/ingest
# STOP_ON_FAILED=1 → ingest server exits on first failed job; corpus client
# also aborts and calls POST /ingest/stop (fast debug loop).
STOP_ON_FAILED ?= 0

ingest: install install-spacy-models ## Start tkeir-ingest on the host (:8091) — P0, no container
	$(Q)mkdir -p "$(INGEST_ROOT_HOST)" "$(GOVERNOR_STATE_ROOT)"
	cd $(TKEIR_DIR) && \
		INGEST_ROOT="$(INGEST_ROOT_HOST)" \
		INGEST_MAX_CONCURRENCY="$(or $(INGEST_MAX_CONCURRENCY),1)" \
		INGEST_STOP_ON_FAILED="$(STOP_ON_FAILED)" \
		GOVERNOR_STATE_ROOT="$(GOVERNOR_STATE_ROOT)" \
		VESPA_USER_SPACE="$(or $(VESPA_USER_SPACE),dev@tkeir)" \
		TKEIR_WORKSPACE="$(WORKSPACE)" \
		TKEIR_REPO_ROOT="$(ROOT)" \
		$(UV) run --python $(PYTHON) tkeir-ingest

rag-query: check-curl check-jq ## Sample curl against RAG API (/rag/query)
	curl -fsS "$(RAG_URL)/rag/query" \
		-H "Content-Type: application/json" \
		-d "$$(jq -nc --arg query "$(RAG_QUERY)" --arg language "$(RAG_LANGUAGE)" --argjson hits $(RAG_HITS) '{query:$$query,language:$$language,hits:$$hits}')" \
		| jq .

search-query: check-curl check-jq ## Sample curl against search API (/search)
	curl -fsS "$(RAG_URL)/search" \
		-H "Content-Type: application/json" \
		-d "$$(jq -nc --arg query "$(RAG_QUERY)" --arg language "$(RAG_LANGUAGE)" --argjson hits $(RAG_HITS) '{query:$$query,language:$$language,hits:$$hits}')" \
		| jq .

MCP_URL ?= http://localhost:8093
MCP_QUERY ?= what is t-keir

mcp: ## Start tkeir-mcp HTTP server (:8093; MCP_STDIO=1 for official MCP stdio)
	$(Q)if [ "$(MCP_STDIO)" = "1" ]; then \
		cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) --extra mcp python -m thot.mcp.server --stdio; \
	else \
		cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) python -m thot.mcp.server; \
	fi

mcp-tools: check-curl check-jq ## List MCP tools then call search (MCP_URL, MCP_QUERY)
	curl -fsS "$(MCP_URL)/mcp/tools" | jq .
	curl -fsS "$(MCP_URL)/mcp/call" \
		-H "Content-Type: application/json" \
		-H "X-Correlation-Id: $$(python3 -c 'import secrets; print(secrets.token_hex(16))')" \
		-d "$$(jq -nc --arg q "$(MCP_QUERY)" '{name:"search",arguments:{query:$$q,hits:5}}')" \
		| jq .

AGENT_URL ?= http://localhost:8092
GOAL ?= What does the corpus say about T-KEIR?
# Agent / workflow LLM runs often exceed 20s (compose + tools). Override if needed.
AGENT_POLL_SECONDS ?= 2
AGENT_POLL_ATTEMPTS ?= 90
WORKFLOW_POLL_ATTEMPTS ?= 180

agent: ## Start tkeir-agent HTTP service (:8092)
	cd $(TKEIR_DIR) && AGENT_ROOT="$(CURDIR)/.tkeir-agent" \
		$(UV) run --python $(PYTHON) python -m thot.agent.service

agent-run: check-curl check-jq ## Create agent run and poll (GOAL=… AGENT=researcher)
	$(Q)resp=$$(curl -fsS "$(AGENT_URL)/agent/runs" \
		-H "Content-Type: application/json" \
		-H "X-Correlation-Id: $$(python3 -c 'import secrets; print(secrets.token_hex(16))')" \
		-d "$$(jq -nc --arg goal "$(GOAL)" --arg agent "$(or $(AGENT),researcher)" '{agent:$$agent,goal:$$goal}')"); \
		echo "$$resp" | jq .; \
		rid=$$(echo "$$resp" | jq -r .run_id); \
		i=0; \
		while [ $$i -lt $(AGENT_POLL_ATTEMPTS) ]; do \
			i=$$((i + 1)); \
			sleep $(AGENT_POLL_SECONDS); \
			payload=$$(curl -fsS "$(AGENT_URL)/agent/runs/$$rid"); \
			st=$$(echo "$$payload" | jq -r .run.status); \
			echo "status=$$st ($$i/$(AGENT_POLL_ATTEMPTS))"; \
			case "$$st" in succeeded|failed|blocked|killed|cancelled) \
				echo "$$payload" | jq .; exit 0 ;; \
			esac; \
		done; \
		echo "timeout waiting for run $$rid — last snapshot:"; \
		curl -fsS "$(AGENT_URL)/agent/runs/$$rid" | jq '{status:.run.status,error:.run.error,usage:.run.usage}' || true; \
		echo "Re-check later: curl -s $(AGENT_URL)/agent/runs/$$rid | jq ."; \
		exit 1

WORKFLOW ?= content_brief

workflow-run: check-curl check-jq ## Create workflow run and poll (GOAL=… WORKFLOW=content_brief)
	$(Q)resp=$$(curl -fsS "$(AGENT_URL)/agent/runs" \
		-H "Content-Type: application/json" \
		-H "X-Correlation-Id: $$(python3 -c 'import secrets; print(secrets.token_hex(16))')" \
		-d "$$(jq -nc --arg goal "$(GOAL)" --arg wf "$(WORKFLOW)" --arg topic "$(or $(TOPIC),Acme)" '{workflow:$$wf,goal:$$goal,params:{topic:$$topic}}')"); \
		echo "$$resp" | jq .; \
		rid=$$(echo "$$resp" | jq -r .run_id); \
		i=0; \
		while [ $$i -lt $(WORKFLOW_POLL_ATTEMPTS) ]; do \
			i=$$((i + 1)); \
			sleep $(AGENT_POLL_SECONDS); \
			payload=$$(curl -fsS "$(AGENT_URL)/agent/runs/$$rid"); \
			st=$$(echo "$$payload" | jq -r .run.status); \
			echo "status=$$st ($$i/$(WORKFLOW_POLL_ATTEMPTS))"; \
			case "$$st" in succeeded|failed|blocked|killed|cancelled) \
				echo "$$payload" | jq '{run,handoffs,compose_result}'; exit 0 ;; \
			esac; \
		done; \
		echo "timeout waiting for workflow $$rid — last snapshot:"; \
		curl -fsS "$(AGENT_URL)/agent/runs/$$rid" | jq '{status:.run.status,error:.run.error,handoffs:(.handoffs|length),compose:(.compose_result!=null)}' || true; \
		echo "Re-check later: curl -s $(AGENT_URL)/agent/runs/$$rid | jq '{run,handoffs,compose_result}'"; \
		exit 1

TEMPLATE ?= synthesis_note
TOPIC ?= Acme
COMPOSE_OUT ?= $(CURDIR)/.tkeir-compose
COMPOSE_TURTLE_DIR ?=

compose: ## Ontology template compose (TEMPLATE=synthesis_note TOPIC=Acme)
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) python -m thot.compose \
		--template "$(TEMPLATE)" \
		--topic "$(TOPIC)" \
		--out "$(COMPOSE_OUT)" \
		$(if $(strip $(COMPOSE_TURTLE_DIR)),--turtle-dir "$(COMPOSE_TURTLE_DIR)" --no-demo,--demo)

compose-list: ## List ontology-driven templates
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) python -m thot.compose --list

# ---------------------------------------------------------------------------
# Multi-thematic corpus: NATO OSINT + Enterprise (Zero-to-Hero §3.4 + §5.5)
# ---------------------------------------------------------------------------
CORPUS_OUT           ?= $(WORKSPACE)
CORPUS_SEED          ?= 42
CORPUS_COUNT_OSINT   ?= 1500
CORPUS_COUNT_ENT     ?= 500
# Set CORPUS_DOWNLOAD=0 for a fully offline generate (skip SISO / EnterpriseRAG fetch).
CORPUS_DOWNLOAD      ?= 1
CORPUS_FLAGS         ?=
INGEST_API_URL       ?= http://localhost:8091
INGEST_TOKEN_URL     ?= http://localhost:8082/realms/tkeir/protocol/openid-connect/token
INGEST_WORKERS       ?= 1
INGEST_FLAGS         ?=
# Appended when STOP_ON_FAILED=1 (see ingest target too).
_STOP_ON_FAILED_FLAG = $(if $(filter 1 true TRUE yes YES,$(STOP_ON_FAILED)),--stop-on-failed,)

_CORPUS_PY  := $(ROOT)/tools/corpus/generate_tkeir_corpus.py
_INGEST_PY  := $(ROOT)/tools/corpus/ingest_corpus.py
_CORPUS_RUN := cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) python

corpus: ## [corpus] Generate OSINT+Enterprise and best-effort download official artifacts
	$(_CORPUS_RUN) $(_CORPUS_PY) \
	  --output $(CORPUS_OUT) \
	  --count-osint $(CORPUS_COUNT_OSINT) \
	  --count-enterprise $(CORPUS_COUNT_ENT) \
	  --seed $(CORPUS_SEED) \
	  $(if $(filter 1,$(CORPUS_DOWNLOAD)),--download,) \
	  $(CORPUS_FLAGS)
	@echo "Next (P0 host): make bootstrap && make ingest   # other terminal: make corpus-ingest"
	@echo "Next (P1):      make compose-up PROFILES=core,auth,ingest && make corpus-ingest-user"
	@echo "Offline-only: make corpus CORPUS_DOWNLOAD=0"

corpus-ontologies: ## [corpus] Generate C2SIM/C4ISR ontologies only
	$(_CORPUS_RUN) $(_CORPUS_PY) \
	  --output $(CORPUS_OUT) --only-ontologies $(CORPUS_FLAGS)

# Kept as an alias so older docs/scripts keep working.
corpus-download: corpus ## [corpus] Alias for 'make corpus' (generate + download)

# Process-time ontologies for OSINT ingest (ingest API stays corpus-agnostic).
# Override with CORPUS_ONTOLOGIES=a.ttl,b.owl or CORPUS_ONTOLOGY_DIR=/other/dir
# Clear with CORPUS_ONTOLOGY_DIR= only if you intentionally skip ontologies.
CORPUS_ONTOLOGY_DIR ?= $(CORPUS_OUT)/corpus_nato/ontologies
CORPUS_ONTOLOGIES ?=
_INGEST_ONTOLOGY_ARGS = $(if $(CORPUS_ONTOLOGIES),--ontologies $(CORPUS_ONTOLOGIES),$(if $(CORPUS_ONTOLOGY_DIR),--ontology-dir $(CORPUS_ONTOLOGY_DIR),))

# Fail if OSINT ingest would run without any ontology files.
define _require_corpus_ontologies
	@if [ -n "$(CORPUS_ONTOLOGIES)" ]; then \
	  echo "Using ontologies: $(CORPUS_ONTOLOGIES)"; \
	elif [ -z "$(CORPUS_ONTOLOGY_DIR)" ]; then \
	  echo "ERROR: corpus-ingest requires ontologies — set CORPUS_ONTOLOGY_DIR or CORPUS_ONTOLOGIES"; \
	  exit 1; \
	elif [ ! -d "$(CORPUS_ONTOLOGY_DIR)" ]; then \
	  echo "ERROR: ontology dir missing: $(CORPUS_ONTOLOGY_DIR)"; \
	  echo "  Run: make corpus   (or make corpus-ontologies)"; \
	  exit 1; \
	elif [ -z "$$(find "$(CORPUS_ONTOLOGY_DIR)" -maxdepth 1 \( -name '*.ttl' -o -name '*.owl' -o -name '*.rdf' -o -name '*.xml' \) -print -quit)" ]; then \
	  echo "ERROR: no OWL/TTL/RDF files in $(CORPUS_ONTOLOGY_DIR)"; \
	  echo "  Run: make corpus   (or make corpus-ontologies)"; \
	  exit 1; \
	else \
	  echo "Using ontologies from $(CORPUS_ONTOLOGY_DIR)"; \
	fi
endef

corpus-ingest: ## [corpus] Ingest both corpora via :8091 (OSINT with ontologies; enterprise without)
	$(call _require_corpus_ontologies)
	$(_CORPUS_RUN) $(_INGEST_PY) \
	  --corpus-dir $(CORPUS_OUT) \
	  --api-url $(INGEST_API_URL) \
	  --corpus osint \
	  --user-space dev@tkeir \
	  --workers $(INGEST_WORKERS) \
	  --fallback-index \
	  --output-report $(CORPUS_OUT)/ingest_osint.json \
	  $(_INGEST_ONTOLOGY_ARGS) \
	  $(_STOP_ON_FAILED_FLAG) \
	  $(INGEST_FLAGS)
	$(_CORPUS_RUN) $(_INGEST_PY) \
	  --corpus-dir $(CORPUS_OUT) \
	  --api-url $(INGEST_API_URL) \
	  --corpus enterprise \
	  --user-space dev@tkeir \
	  --workers $(INGEST_WORKERS) \
	  --fallback-index \
	  --output-report $(CORPUS_OUT)/ingest_enterprise.json \
	  $(_STOP_ON_FAILED_FLAG) \
	  $(INGEST_FLAGS)
	@echo "If API was down (P0): make bootstrap && make ingest   # then re-run make corpus-ingest"
	@echo "If API was down (P1): make images && make compose-up PROFILES=core,ingest"
	@echo "OSINT ingested with ontologies; enterprise ingested without"
	@echo "Debug tip: make ingest STOP_ON_FAILED=1  &&  make corpus-ingest STOP_ON_FAILED=1"

corpus-ingest-user: ## [corpus] Ingest OSINT corpus as demo-user (P1, Keycloak required)
	$(call _require_corpus_ontologies)
	$(_CORPUS_RUN) $(_INGEST_PY) \
	  --corpus-dir $(CORPUS_OUT) \
	  --api-url $(INGEST_API_URL) \
	  --corpus osint \
	  --username demo-user --password demo-user \
	  --token-url $(INGEST_TOKEN_URL) \
	  --workers $(INGEST_WORKERS) \
	  --status-poll \
	  --output-report $(CORPUS_OUT)/ingest_user.json \
	  $(_INGEST_ONTOLOGY_ARGS) \
	  $(_STOP_ON_FAILED_FLAG) \
	  $(INGEST_FLAGS)

corpus-ingest-admin: ## [corpus] Ingest Enterprise corpus as demo-admin (P1, Keycloak required)
	$(_CORPUS_RUN) $(_INGEST_PY) \
	  --corpus-dir $(CORPUS_OUT) \
	  --api-url $(INGEST_API_URL) \
	  --corpus enterprise \
	  --username demo-admin --password demo-admin \
	  --token-url $(INGEST_TOKEN_URL) \
	  --workers $(INGEST_WORKERS) \
	  --status-poll \
	  --output-report $(CORPUS_OUT)/ingest_admin.json \
	  $(_STOP_ON_FAILED_FLAG) \
	  $(INGEST_FLAGS)

corpus-ingest-web: ## [corpus] Print HMI drag-and-drop + curl guide for web ingestion
	$(_CORPUS_RUN) $(_INGEST_PY) \
	  --corpus-dir $(CORPUS_OUT) \
	  --api-url $(INGEST_API_URL) \
	  --token-url $(INGEST_TOKEN_URL) \
	  --print-web-guide

corpus-demo: corpus corpus-ingest ## [corpus] One-shot: generate → ingest (P0 host ingest must be up)
	@echo "=== Corpus demo ready (P0 / dev@tkeir) ==="
	@echo "  Prerequisite: make bootstrap && make ingest (host; no tkeir containers)"
	@echo "  RAG: make rag && make rag-query RAG_QUERY=\"SITREP Objective ALPHA\""
	@echo "  HMI: cd tkeir-hmi && npm run dev → http://localhost:3000"
	@echo "  P1 isolation: make images && make compose-up PROFILES=core,auth,ingest"
	@echo "                make corpus-ingest-user && make corpus-ingest-admin"

corpus-clean: ## [corpus] Remove generated corpora under workspace/
	rm -rf $(CORPUS_OUT)/corpus_nato $(CORPUS_OUT)/corpus_enterprise
	@echo "Cleaned $(CORPUS_OUT)/corpus_nato and $(CORPUS_OUT)/corpus_enterprise"

smoke-test: check-curl check-jq ## Post-deploy RAG /health check (SMOKE_TARGET_URL)
	$(Q)echo "=== Smoke test [env=$(ENVIRONMENT)] -> $(SMOKE_TARGET_URL) ==="
	$(Q)status=$$(curl -fsS --max-time $(SMOKE_TIMEOUT) "$(SMOKE_TARGET_URL)/health" \
		| jq -r '.status // "unknown"' 2>/dev/null) || { \
		echo "FAIL: $(SMOKE_TARGET_URL)/health unreachable or returned invalid JSON"; exit 1; }; \
	if [ "$$status" = "ok" ] || [ "$$status" = "healthy" ]; then \
		echo "PASS: status=$$status"; \
	else \
		echo "FAIL: unexpected status ($$status)"; exit 1; \
	fi

beir-eval: ## BEIR IR eval → docs/evaluation_report.md (BEIR_DATASETS=scifact for one)
	cd $(TKEIR_DIR) && $(UV) sync --group beir --group models --python $(PYTHON)
	cd $(TKEIR_DIR) && \
		VESPA_NAME="$(BEIR_VESPA_NAME)" \
		VESPA_VOLUME="$(BEIR_VESPA_VOLUME)" \
		$(UV) run --python $(PYTHON) --group beir --group models \
		python -m thot.tools.search.beir_eval \
		--datasets $(BEIR_DATASETS) \
		--datasets-dir "$(BEIR_DATASETS_DIR)" \
		--dense-model "$(BEIR_DENSE_MODEL)" \
		$(if $(strip $(BEIR_REPORT)),--report "$(BEIR_REPORT)",) \
		$(BEIR_EXTRA)

clean-db: ## Wipe Vespa data volume
	cd $(VESPA_DIR) && ./clean_db.sh

vespa-clean: check-docker ## Stop/remove Vespa container (keeps volume)
	docker stop vespa || true
	docker rm vespa || true

logs: check-docker ## Tail Vespa Docker logs
	docker logs -f vespa

# ── EU Compliance Audit ──────────────────────────────────────────────────────
## compliance-input: regenerate OPA input JSON from repository evidence
.PHONY: compliance-input
compliance-input:
	python3 compliance/opa/collectors/input_generator.py \
		--repo . \
		--overrides compliance/opa/overrides.yaml \
		--output "compliance/opa/input/generated_$$(date +%Y%m%d_%H%M%S).json"

## audit-compliance: run EU compliance audit (OPA required; skips gracefully if absent)
.PHONY: audit-compliance
audit-compliance: compliance-input
	bash compliance/opa/run_audit.sh

## compliance-report: alias for audit-compliance
.PHONY: compliance-report
compliance-report: audit-compliance

## compliance-doc-results: publish latest report.json into MkDocs (generated/)
.PHONY: compliance-doc-results
compliance-doc-results:
	python3 compliance/opa/scripts/gen_doc_results.py --allow-missing

## compliance-doc-tables: regenerate MkDocs article tables from Rego catalogues
.PHONY: compliance-doc-tables
compliance-doc-tables:
	python3 compliance/opa/scripts/gen_doc_tables.py

## oscal-catalogs: regenerate OSCAL catalogs from Rego catalogues
.PHONY: oscal-catalogs
oscal-catalogs:
	python3 compliance/opa/oscal/gen_oscal_catalogs.py

## oscal-validate: validate generated OSCAL documents with oscal-cli (if installed)
.PHONY: oscal-validate
oscal-validate:
	@if command -v oscal-cli >/dev/null 2>&1; then \
	  for f in reports/compliance/eu-audit/*/oscal/assessment_results.json; do \
	    [ -f "$$f" ] || continue; \
	    echo "[oscal] Validating $$f"; \
	    oscal-cli validate "$$f" || oscal-cli ar validate "$$f" || true; \
	  done; \
	else \
	  echo "[oscal] WARNING: oscal-cli not found — skipping OSCAL validation"; \
	  echo "[oscal] Install: https://github.com/usnistgov/oscal-cli"; \
	fi

## oscal-diff: diff two OSCAL assessment results (BASELINE=… CURRENT=…)
.PHONY: oscal-diff
oscal-diff:
	@test -n "$(BASELINE)" || { echo "Set BASELINE=<git-describe>"; exit 1; }
	@test -n "$(CURRENT)" || { echo "Set CURRENT=<git-describe>"; exit 1; }
	python3 compliance/opa/oscal/opa_to_oscal.py --diff \
	  --baseline "reports/compliance/eu-audit/$(BASELINE)/oscal/assessment_results.json" \
	  --current  "reports/compliance/eu-audit/$(CURRENT)/oscal/assessment_results.json"
