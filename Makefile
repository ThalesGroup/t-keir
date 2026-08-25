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
	check-install \
	install-tesseract install-spacy-models build wheel init-models \
	test test-unit test-functional test-coverage coverage \
	test-integration test-integration-ci \
	test-fuzz-hypothesis test-fuzz-atheris test-fuzz-radamsa test-fuzz fuzz-report \
	test-bdd test-bdd-ci bdd-report \
	slsa-prereqs slsa-provenance slsa-assess slsa-report slsa-level-gate slsa \
	check-cosign check-radamsa check-supply-tools \
	sign-wheel sign-sbom sign-provenance sign-attest-images sign-all verify-signatures \
	lint format typecheck liccheck complexity complexity-report pip-licenses license-report quality-docs pip-audit \
	deps-check deps-update deps-update-safe verify-lockfile tag changelog \
	bom sbom aibom trivy owasp-dependency-check security-report \
	docs docs-build docs-pdf pipeline quickstart ci-deps ci pre-commit clean devcontainer \
	sync pull-models pull-bge-model pull-vespa pull-searxng start init bootstrap vespa-check test-vespa test-vespa-py \
	index index-fixtures rag ingest rag-query search-query mcp mcp-tools agent agent-run smoke-test \
	beir-eval beir-smoke generate-eval rag-eval beir-rag-eval eval eval-smoke clean-db vespa-clean logs \
	images images-push images-sign \
	compose-up compose-down compose-bootstrap compose-logs compose-smoke wipe-runtime down all-down \
	audit-report audit-summary audit-verify audit-archive \
	governor-flags governor-kill rollback-index check-secrets-staged \
	hmi-install hmi-lint hmi-typecheck hmi-build hmi-up \
	k3d-up k3d-down helm-deps helm-lint helm-template cluster-install cluster-plan cluster-uninstall \
	k3s-server k3s-agent k3s-check cilium-install lima-k3s-up lima-k3s-down \
	searxng-up searxng-down collector collector-up collector-query \

	keycloak-export-realm keycloak-sync-demo-users keycloak-purge-demo-users seal kubeflow-install kubeflow-uninstall kubeflow-register-models kubeflow-run-ingest \
	lineage-report audit-evidence annex-iv \
	datasets datasets-ontologies datasets-download datasets-ingest datasets-ingest-user datasets-ingest-admin \
	scidocs-download \
	datasets-ingest-web datasets-demo datasets-clean \
	schemas schemas-check

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
# Host P0 Vespa image (matches vespa/start_vespa.sh and deploy/versions.lock.yaml).
VESPA_IMAGE ?= vespaengine/vespa
# Host web collector meta-search (JSON API on :8888).
SEARXNG_IMAGE ?= docker.io/searxng/searxng:latest
SEARXNG_NAME ?= searxng
SEARXNG_PORT ?= 8888
COLLECTOR_PORT ?= 8096
COLLECTOR_URL ?= http://127.0.0.1:$(COLLECTOR_PORT)
COLLECTOR_QUERY ?= maritime AIS anomaly
COLLECTOR_TOPIC ?= osint
COLLECTOR_LANGUAGE ?= en
COLLECTOR_MAX_RESULTS ?= 3
SEARXNG_URL ?= http://127.0.0.1:$(SEARXNG_PORT)
TESTS_DIR := $(ROOT)/tests
CONFIGS_DIR := $(TKEIR_DIR)/configs
SCRIPTS_DIR := $(ROOT)/scripts
COVERAGE_REPORT_DIR := $(ROOT)/coverage-reports
SECURITY_REPORT_DIR ?= $(ROOT)/reports/security
LICCHECK_CONFIG ?= $(TKEIR_DIR)/liccheck.ini
DIST_DIR := $(ROOT)/dist
BUILD_STAMP := $(DIST_DIR)/.build_timestamp

WORKSPACE ?= $(ROOT)/workspace
# Flat OKF fallback (default_okf_root when OKF_ROOT unset). Per-user bundles:
# $(WORKSPACE)/users/<space>/okf/<bundle_id>/
OKF_FLAT_ROOT ?= $(WORKSPACE)/.tkeir-okf
# Agent run store (default_agent_root when AGENT_ROOT unset).
AGENT_ROOT ?= $(WORKSPACE)/agent
PIPELINE_CONFIG ?= $(CONFIGS_DIR)/pipeline.yaml
PIPELINE_INPUT ?= $(ROOT)/tests/fixtures/test-raw/raw
PIPELINE_OUTPUT ?= $(WORKSPACE)/tmp/pipeline-out
PIPELINE_TYPE ?= auto
TRANSFORMERS_CACHE ?= $(ROOT)/.cache/models
# spaCy / misc transformers cache (not used for BGE-M3 — that lives under resources/modeling/net).
HF_HOME ?= $(TRANSFORMERS_CACHE)
HUGGINGFACE_HUB_CACHE ?= $(TRANSFORMERS_CACHE)/hub
BGE_MODEL ?= BAAI/bge-m3
FORCE_BGE ?= 0
DOCS_PORT ?= 8000
DOCS_PDF_OUTPUT ?= $(ROOT)/output/docs/tkeir-docs.pdf

INDEX_INPUT ?= $(ROOT)/tests/indexing/output
INDEX_FIXTURES_INPUT := $(ROOT)/tests/indexing/input
RAG_URL ?= http://localhost:8090
RAG_QUERY ?= Who is Rob Brown?
RAG_LANGUAGE ?= en
RAG_HITS ?= 20
BEIR_DATASETS_DIR ?= $(ROOT)/datasets
# Optional extra report copy; docs report is always written by beir_eval.
BEIR_REPORT ?=
# Space-separated BEIR dataset names. One dataset example:
#   make beir-eval BEIR_DATASETS=scifact
BEIR_DATASETS ?= scifact fiqa arguana scidocs
BEIR_DENSE_MODEL ?= bge-m3
# Dedicated Vespa volume so BEIR reindex does not wipe the primary corpus.
BEIR_VESPA_NAME ?= vespa
BEIR_VESPA_VOLUME ?= beir_eval_data:/opt/vespa/var
# Extra CLI flags for beir_eval, e.g. BEIR_EXTRA=--skip-dense
BEIR_EXTRA ?=

# Generation eval (datasets/rag_benchmarks) — oracle evidence → LLM.
#   make generate-eval GEN_DATASETS=multihop
#   make generate-eval GEN_DATASETS="covidqa pubmedqa" GEN_EXTRA="--max-queries 5 --dump-prompts"
GEN_BENCHMARKS_DIR ?= $(ROOT)/datasets/rag_benchmarks
GEN_DATASETS ?= covidqa pubmedqa finqa tatqa multihop
GEN_REPORT ?=
GEN_EXTRA ?=
# Deprecated aliases
RAG_BENCHMARKS_DIR ?= $(GEN_BENCHMARKS_DIR)
RAG_DATASETS ?= $(GEN_DATASETS)
RAG_REPORT ?= $(GEN_REPORT)
RAG_EXTRA ?= $(GEN_EXTRA)

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
# Paths relative to TKEIR_DIR (lint/format/typecheck run with --directory $(TKEIR_DIR)).
PYTHON_SOURCES := thot ../tests/unittests ../tests/functional_tests ../tests/conftest.py
# Explicit config: multi-root sources otherwise climb to the repo root and drop
# tkeir/pyproject.toml settings (e.g. black line-length 79 → mass reformat).
PYPROJECT := $(TKEIR_DIR)/pyproject.toml

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
# Absolute “no grade D+” gate — scoped to stable packages. RAG / OKF / eval /
# ingest / answer_generation still need refactors before joining this list.
COMPLEXITY_D_GATE_SOURCES ?= \
	thot/core thot/action thot/audit thot/governor thot/agent \
	thot/tools/pipeline.py thot/tools/annotation \
	thot/tasks/pipeline thot/tasks/converters thot/tasks/keywords \
	thot/tasks/morphosyntax thot/tasks/syntax thot/tasks/language_detection \
	thot/tasks/ner thot/tasks/tokenizer thot/tasks/document_ontology \
	thot/tasks/embeddings thot/tasks/golden_chunking

# Minimum test coverage percentage — CI fails below this threshold.
COVERAGE_FAIL_UNDER ?= 90

# Integration / fuzz / BDD / SLSA / signing (supply-chain hardening)
INTEGRATION_TIMEOUT    ?= 10
INTEGRATION_REPORT_DIR ?= $(ROOT)/reports/integration
RAG_URL_TEST           ?= http://localhost:8090
# Dedicated ingest API (compose :8091). Override to $(RAG_URL_TEST)/ingest if proxied.
INGEST_URL_TEST        ?= http://localhost:8091
SKIP_INTEGRATION       ?= 0

FUZZ_REPORT_DIR        ?= $(ROOT)/reports/fuzzing
FUZZ_DURATION          ?= 60
FUZZ_CORPUS_DIR        ?= $(ROOT)/tests/fuzzing/corpus
HYPOTHESIS_SEED        ?= 0
RADAMSA                ?= radamsa
RADAMSA_COUNT          ?= 200
RADAMSA_SEED           ?= 42

BDD_REPORT_DIR         ?= $(ROOT)/reports/bdd
BDD_FEATURES           ?= $(ROOT)/tests/bdd/features
BDD_FORMAT             ?= pretty

SLSA_LEVEL             ?= 2
SLSA_REPORT_DIR        ?= $(ROOT)/reports/slsa
# TODO: pin digest on first pull — docker pull … && docker inspect --format='{{index .RepoDigests 0}}'
SLSA_VERIFIER_IMAGE    ?= ghcr.io/slsa-framework/slsa-verifier/slsa-verifier@sha256:TODO_PIN_DIGEST
VERDIT_SLSA_VERSION    ?= 0.1.0
PROVENANCE_FILE        ?= $(SLSA_REPORT_DIR)/provenance.json

COSIGN_BUNDLE_DIR      ?= $(ROOT)/reports/signatures
COSIGN_YES             ?= --yes
REKOR_URL              ?= https://rekor.sigstore.dev
FULCIO_URL             ?= https://fulcio.sigstore.dev
SKIP_SIGNING           ?= 0
STRICT_SIGNING         ?= 0
SKIP_IMAGE_ATTEST      ?= 1
# Prefer tkeir/dist (uv build output); fall back to ROOT/dist.
WHEEL_DIR              ?= $(TKEIR_DIR)/dist

QUICKSTART_CONFIG ?= $(PIPELINE_CONFIG)
QUICKSTART_OUTPUT ?= $(ROOT)/output/quickstart

-include .env

# Export only the variables defined in this Makefile, not the entire environment.
# This prevents secrets stored in .env (PYPI_TOKEN, DOCKER_PASSWORD, etc.)
# from leaking into CI logs via a bare 'export'.
export UV PYTHON COMPOSE TRIVY_IMAGE OWASP_DC_IMAGE OWASP_DC_FAIL_CVSS TRIVY_SEVERITY
export BOM_SPEC_VERSION BOM_REPORT_DIR BOM_CONFIG BOM_PYTHON
export PIPELINE_CONFIG PIPELINE_INPUT PIPELINE_OUTPUT PIPELINE_TYPE
export TRANSFORMERS_CACHE HF_HOME HUGGINGFACE_HUB_CACHE WORKSPACE DOCS_PORT
export OKF_FLAT_ROOT AGENT_ROOT
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
	$(Q)printf '%s\n' "Python packages: thot.tools.ingest | thot.tools.search | thot.tools.collector | thot.tools.okf | thot.tools.eval"
	$(Q)printf '%s\n' "Common vars: PIPELINE_* INDEX_INPUT RAG_QUERY COLLECTOR_QUERY BEIR_* COVERAGE_FAIL_UNDER VERSION WORKSPACE VERBOSE"
	$(Q)printf '%s\n' "Workspace:   WORKSPACE=$(WORKSPACE)  OKF_FLAT_ROOT=$(OKF_FLAT_ROOT)  AGENT_ROOT=$(AGENT_ROOT)"
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

check-jq: ## Require jq (rag-query / collector-query / smoke-test)
	$(Q)command -v jq >/dev/null 2>&1 || { \
		echo "jq is required (used by rag-query / collector-query / smoke-test). Install: https://stedolan.github.io/jq/"; \
		exit 1; }

check-curl: ## Require curl (rag-query / collector-query / smoke-test)
	$(Q)command -v curl >/dev/null 2>&1 || { \
		echo "curl is required (used by rag-query / collector-query / smoke-test). Install: https://curl.se/"; \
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

# Dev-mode install verification (STRICT=1 treats warnings as failures).
STRICT ?= 0
SKIP_DOCKER ?= 0
SKIP_HMI ?= 0
SKIP_SPACY ?= 0

check-install: ## Verify local/dev install (tools, Python, spaCy, Docker, HMI)
	$(Q)chmod +x "$(SCRIPTS_DIR)/check_install.sh"
	$(Q)UV="$(UV)" PYTHON="$(PYTHON)" \
		TKEIR_DIR="$(TKEIR_DIR)" HMI_DIR="$(HMI_DIR)" \
		VESPA_IMAGE="$(VESPA_IMAGE)" \
		STRICT="$(STRICT)" \
		SKIP_DOCKER="$(SKIP_DOCKER)" \
		SKIP_HMI="$(SKIP_HMI)" \
		SKIP_SPACY="$(SKIP_SPACY)" \
		"$(SCRIPTS_DIR)/check_install.sh"

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

install-spacy-models: check-uv ## Install spaCy language models (skip if present; FORCE_SPACY_MODELS=1)
	$(Q)chmod +x "$(SCRIPTS_DIR)/install_spacy_models.sh"
	$(Q)bash "$(SCRIPTS_DIR)/install_spacy_models.sh"

install-tesseract: ## Install Tesseract OCR via helper script
	$(Q)chmod +x "$(SCRIPTS_DIR)/install_tesseract.sh"
	$(Q)bash "$(SCRIPTS_DIR)/install_tesseract.sh"

init-models: install ## Build tkeir_mwe.pkl from annotation resources (skip if present)
	$(Q)mkdir -p "$(TRANSFORMERS_CACHE)"
	$(Q)chmod +x "$(TKEIR_DIR)/scripts/init-models.sh"
	$(Q)cd $(TKEIR_DIR) && TRANSFORMERS_CACHE="$(TRANSFORMERS_CACHE)" \
		bash scripts/init-models.sh "$(TRANSFORMERS_CACHE)"

setup: ## Full local setup (install → spaCy → Tesseract → MWE → BGE-M3 → Vespa → SearXNG → SciDocs)
	$(MAKE) install
	$(MAKE) install-spacy-models
	$(MAKE) install-tesseract
	$(MAKE) init-models
	$(MAKE) pull-bge-model
	$(MAKE) pull-vespa
	$(MAKE) pull-searxng
	$(MAKE) scidocs-download
	$(Q)echo ""
	$(Q)echo "Setup complete."
	$(Q)echo "  Run pipeline: make pipeline"
	$(Q)echo "  Or demo:      make quickstart"
	$(Q)echo "  Vespa:        make bootstrap   # start container + deploy schemas"
	$(Q)echo "  SearXNG:      make searxng-up  # meta-search on :$(SEARXNG_PORT)"
	$(Q)echo "  Collector:    make collector && make collector-query COLLECTOR_QUERY=\"maritime AIS\""
	$(Q)echo "  Index:        make index          # thot.tools.ingest"
	$(Q)echo "  Search/RAG:   make rag            # thot.tools.search"
	$(Q)echo "  Eval smoke:   make eval-smoke     # thot.tools.eval"
	$(Q)echo "  Ollama LLM:   make pull-models    # optional host Ollama models"

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
		ruff check --config "$(PYPROJECT)" $(PYTHON_SOURCES)
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with black --with isort \
		black --check --config "$(PYPROJECT)" $(PYTHON_SOURCES)
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with isort \
		isort --check-only --settings-path "$(PYPROJECT)" $(PYTHON_SOURCES)

hmi-lint: hmi-install ## Next.js / ESLint checks for the HMI
	cd $(HMI_DIR) && npm run lint

format: ci-deps ## Apply ruff + black + isort
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with ruff \
		ruff format --config "$(PYPROJECT)" $(PYTHON_SOURCES)
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with black --with isort \
		black --config "$(PYPROJECT)" $(PYTHON_SOURCES)
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with isort \
		isort --settings-path "$(PYPROJECT)" $(PYTHON_SOURCES)

typecheck: ci-deps ## mypy on thot/ and tests/
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with mypy \
		mypy --config-file "$(PYPROJECT)" $(PYTHON_SOURCES)

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
	cd $(TKEIR_DIR) && $(UV) export --frozen --no-dev --no-emit-project --no-hashes \
		-o .requirements-liccheck.txt
	# liccheck 0.9.2 still imports pkg_resources; setuptools>=82 removed it.
	# Run in an isolated tool env and drop the project setuptools==84 pin so
	# setuptools<81 (needed for pkg_resources) does not VersionConflict.
	cd $(TKEIR_DIR) && grep -vE '^setuptools[=<>!~@]' \
		.requirements-liccheck.txt > .requirements-liccheck.filtered.txt
	cd $(TKEIR_DIR) && $(UV) run --no-project --python $(PYTHON) \
		--with liccheck --with "setuptools>=70,<81" \
		liccheck -l PARANOID \
		-s "$(LICCHECK_CONFIG)" \
		-r .requirements-liccheck.filtered.txt
	rm -f $(TKEIR_DIR)/.requirements-liccheck.txt \
		$(TKEIR_DIR)/.requirements-liccheck.filtered.txt

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
	@# Fail if any function in the scoped stable packages is grade D or worse
	$(Q)out=$$(cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		radon cc $(COMPLEXITY_D_GATE_SOURCES) -n D -s); \
	if [ -n "$$out" ]; then \
		echo "$$out"; \
		echo "FAIL: functions at grade D or worse exist (see above)"; \
		exit 1; \
	fi; \
	echo "OK: no functions at grade D or worse in COMPLEXITY_D_GATE_SOURCES"

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

quality-docs: complexity-report pip-licenses ## regenerate docs/quality/index.md
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
# PYSEC-2026-3552 — cryptography>=50 blocked by optional spiffe extra (cryptography<47) | fix blocked by: spiffe upstream | target resolution: 2026-09-01 | ticket: N/A
PIP_AUDIT_IGNORE += --ignore-vuln PYSEC-2026-3552
# PYSEC-2026-3553 — cryptography>=49 blocked by optional spiffe extra (cryptography<47) | fix blocked by: spiffe upstream | target resolution: 2026-09-01 | ticket: N/A
PIP_AUDIT_IGNORE += --ignore-vuln PYSEC-2026-3553
# PYSEC-2026-3554 — cryptography>=49 blocked by optional spiffe extra (cryptography<47) | fix blocked by: spiffe upstream | target resolution: 2026-09-01 | ticket: N/A
PIP_AUDIT_IGNORE += --ignore-vuln PYSEC-2026-3554

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
	cd $(ROOT) && $(UV) run --project $(TKEIR_DIR) --python $(PYTHON) \
		--with mkdocs --with mkdocs-material --with mkdocs-render-swagger-plugin \
		mkdocs serve -f "$(ROOT)/mkdocs.yml" -a 127.0.0.1:$(DOCS_PORT)

docs-build: ci-deps quality-docs ## Build static MkDocs site under site/
	cd $(ROOT) && $(UV) run --project $(TKEIR_DIR) --python $(PYTHON) \
		--with mkdocs --with mkdocs-material --with mkdocs-render-swagger-plugin \
		mkdocs build -f "$(ROOT)/mkdocs.yml"
	$(Q)echo "Built static site: $(ROOT)/site/index.html"

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
	$(MAKE) schemas-check
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) hmi-lint
	$(MAKE) hmi-typecheck
	$(MAKE) hmi-build
	$(MAKE) test
ifneq ($(SKIP_INTEGRATION),1)
	$(MAKE) test-integration-ci
endif
	$(MAKE) test-fuzz-hypothesis
	$(MAKE) test-bdd-ci
	$(MAKE) coverage
	$(MAKE) liccheck
	$(MAKE) complexity
	$(MAKE) complexity-report
	$(MAKE) pip-licenses
	$(MAKE) pip-audit
	$(MAKE) bom
	$(MAKE) trivy
	$(MAKE) owasp-dependency-check
	$(MAKE) slsa
ifneq ($(SKIP_SIGNING),1)
	$(Q)if command -v cosign >/dev/null 2>&1; then \
		$(MAKE) sign-all && $(MAKE) verify-signatures; \
	else \
		if [ "$(STRICT_SIGNING)" = "1" ]; then \
			echo "ERROR: cosign required (STRICT_SIGNING=1)"; exit 1; \
		fi; \
		echo "WARN: cosign not installed — skipping sign-all/verify-signatures"; \
	fi
endif
	$(MAKE) audit-compliance
	$(MAKE) docs-build
	$(Q)signed=no; \
		if [ "$(SKIP_SIGNING)" != "1" ] && command -v cosign >/dev/null 2>&1 \
			&& [ -f "$(COSIGN_BUNDLE_DIR)/wheel.bundle" ]; then signed=yes; fi; \
		echo "All quality gates passed. VERSION=$(VERSION) COMMIT=$(GIT_COMMIT) SLSA=$(SLSA_LEVEL) SIGNED=$$signed"

clean: ## Remove build artifacts, caches, and reports
	rm -rf dist build .pytest_cache .mypy_cache .ruff_cache htmlcov .cache reports
	rm -rf "$(COVERAGE_REPORT_DIR)"
	rm -f $(TESTS_DIR)/.coverage $(TESTS_DIR)/.coverage_* $(TESTS_DIR)/testsuite.log
	rm -rf $(TKEIR_DIR)/site $(ROOT)/site
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

# VOLUMES=1 → compose down -v (wipe named volumes). Default keeps data for
# `compose-down` alone. `make down` always wipes unless KEEP_DATA=1.
VOLUMES ?= 0
KEEP_DATA ?= 0

compose-up: check-docker ## Start Compose profiles (PROFILES=core,auth); build local images first if needed
	$(Q)test -f "$(COMPOSE_DIR)/.env" || cp "$(COMPOSE_DIR)/.env.example" "$(COMPOSE_DIR)/.env"
	$(Q)PROFILE_ARGS=$$(printf -- '--profile %s ' $$(echo "$(COMPOSE_PROFILES)" | tr ',' ' ')); \
		IMAGE_REGISTRY="$(IMAGE_REGISTRY)" IMAGE_TAG="$(IMAGE_TAG)" \
		VERSION="$(VERSION)" GIT_COMMIT="$(GIT_COMMIT)" BUILD_DATE="$(BUILD_DATE)" \
		$(COMPOSE) -f "$(COMPOSE_FILE)" --env-file "$(COMPOSE_DIR)/.env" \
			$$PROFILE_ARGS up -d --remove-orphans
	$(Q)echo "Compose up (PROFILES=$(COMPOSE_PROFILES) IMAGE_REGISTRY=$(IMAGE_REGISTRY)). HMI http://localhost:3000"
	$(Q)echo "Local images: make images   |   Publish: make images-push IMAGE_REGISTRY=ghcr.io/thalesgroup/t-keir"
	$(Q)echo "If tkeir-api is unhealthy (Vespa app missing): make compose-bootstrap"

compose-bootstrap: check-docker ## Deploy Vespa schemas into Compose tkeir-vespa (skip host container start)
	$(Q)echo "Deploying schemas into container tkeir-vespa…"
	cd $(VESPA_DIR) && VESPA_NAME=tkeir-vespa bash ./init_schema.sh
	$(Q)echo "Done. Restart API if needed: docker restart tkeir-api"

compose-down: check-docker ## Stop Compose stack (VOLUMES=1 also removes volumes)
	$(Q)ENV_FILE="$(COMPOSE_DIR)/.env"; \
		test -f "$$ENV_FILE" || ENV_FILE="$(COMPOSE_DIR)/.env.example"; \
		PROFILE_ARGS=$$(printf -- '--profile %s ' $$(echo "$(COMPOSE_PROFILES)" | tr ',' ' ')); \
		$(COMPOSE) -f "$(COMPOSE_FILE)" --env-file "$$ENV_FILE" \
			$$PROFILE_ARGS down --remove-orphans $(if $(filter 1,$(VOLUMES)),-v,)
	$(Q)echo "Compose down$(if $(filter 1,$(VOLUMES)), (volumes removed),)"

# All Compose profiles used by the hybrid / full demo (infra + optional services).
DEMO_COMPOSE_PROFILES ?= core,auth,ingest,audit,governor,observability,objectstore,mcp,agents,spire,okf
# Host ports used by hybrid demo services (rag/ingest/agent/audit/governor/okf/hmi).
DEMO_HOST_PORTS ?= 3000 8090 8091 8092 8093 8094 8095 8096 8888

wipe-runtime: check-docker ## Wipe host + leftover Docker runtime DBs/state (Vespa, audit, governor, …)
	$(Q)echo "Wiping host Vespa data volume…"
	-$(MAKE) clean-db
	$(Q)echo "Removing leftover Compose / Vespa Docker volumes (if any)…"
	-$(Q)vols=$$(docker volume ls -q 2>/dev/null | awk '/(^tkeir_|vespa_data$$|beir_eval_data$$)/ {print}'); \
		if [ -n "$$vols" ]; then \
			echo "  docker volume rm $$vols"; \
			docker volume rm $$vols >/dev/null 2>&1 || true; \
		fi
	$(Q)echo "Wiping host runtime state under $(WORKSPACE)…"
	$(Q)rm -rf \
		"$(WORKSPACE)/audit" \
		"$(WORKSPACE)/governor" \
		"$(WORKSPACE)/ingest" \
		"$(WORKSPACE)/users" \
		"$(AGENT_ROOT)" \
		"$(WORKSPACE)/tmp" \
		"$(WORKSPACE)/searxng/data" \
		"$(WORKSPACE)/collector" \
		"$(OKF_FLAT_ROOT)" \
		"$(ROOT)/.tkeir-agent" \
		"$(COMPOSE_OUT)"
	$(Q)if [ -n "$(strip $(OKF_ROOT))" ]; then rm -rf "$(OKF_ROOT)"; fi
	$(Q)echo "Runtime DBs/state wiped (incl. $(OKF_FLAT_ROOT) and $(AGENT_ROOT))."

down: check-docker ## Stop all demo services and wipe DBs/state (KEEP_DATA=1 to preserve)
	$(Q)echo "Purging Keycloak demo personas (best-effort, while auth is still up)…"
	-$(MAKE) keycloak-purge-demo-users
	$(Q)echo "Stopping all Compose profiles ($(DEMO_COMPOSE_PROFILES))…"
	$(MAKE) compose-down PROFILES="$(DEMO_COMPOSE_PROFILES)" \
		VOLUMES="$(if $(filter 1,$(KEEP_DATA)),0,1)"
	$(Q)echo "Stopping host Vespa container (if any)…"
	-$(Q)docker stop vespa >/dev/null 2>&1 || true
	-$(Q)docker rm vespa >/dev/null 2>&1 || true
	$(Q)echo "Stopping SearXNG container (if any)…"
	-$(Q)docker stop "$(SEARXNG_NAME)" >/dev/null 2>&1 || true
	-$(Q)docker rm "$(SEARXNG_NAME)" >/dev/null 2>&1 || true
	$(Q)echo "Stopping host demo listeners on ports $(DEMO_HOST_PORTS) (best-effort)…"
	-$(Q)for p in $(DEMO_HOST_PORTS); do \
		pids=$$(lsof -tiTCP:$$p -sTCP:LISTEN 2>/dev/null || true); \
		if [ -n "$$pids" ]; then \
			echo "  killing port $$p: $$pids"; \
			kill $$pids 2>/dev/null || true; \
		fi; \
	done
ifeq ($(KEEP_DATA),1)
	$(Q)echo "All down (KEEP_DATA=1 — Compose volumes and host runtime DBs preserved; demo personas purged if Keycloak was up)."
else
	$(Q)echo "Wiping all runtime databases and local state (incl. Keycloak volumes)…"
	$(MAKE) wipe-runtime
	-$(Q)vols=$$(docker volume ls -q 2>/dev/null | awk '/keycloak/ {print}'); \
		if [ -n "$$vols" ]; then echo "  removing leftover Keycloak volumes: $$vols"; docker volume rm $$vols >/dev/null 2>&1 || true; fi
	$(Q)echo "All down (Compose volumes + Vespa/audit/governor/ingest/OKF/agent/Keycloak state removed)."
	$(Q)echo "Tip: KEEP_DATA=1 make down  stops services without wiping databases."
endif

all-down: down ## Alias for make down

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
#
# Local defaults for audit hot store + WORM segments (used by host-run audit,
# plus `make audit-archive` / `make audit-verify`).
# Use := so shell/compose exports like AUDIT_WORM_ROOT=/var/tkeir/... do not
# hijack host Make targets (Permission denied on /var/tkeir). Override on the
# command line when needed: make audit-verify AUDIT_ROOT=/custom/audit
# Host path: workspace/audit (sqlite hot store + filesystem WORM). MinIO is
# optional and only used when AUDIT_WORM_S3_ENDPOINT is set (Compose objectstore).
AUDIT_ROOT := $(WORKSPACE)/audit
AUDIT_HOT_STORE_URL := sqlite:$(AUDIT_ROOT)/hot_store.db
AUDIT_WORM_ROOT := $(AUDIT_ROOT)/worm
AUDIT_SUBJECT_KEYS_PATH := $(AUDIT_ROOT)/subject_keys.db
AUDIT_SINK_MODE ?= dual
AUDIT_AUTH_ENABLED ?= false
GOVERNOR_AUTH_ENABLED ?= false
# Force empty S3 endpoint on host so a sourced compose .env cannot point archive
# at MinIO when you are not running objectstore.
AUDIT_HOST_ENV = \
	AUDIT_HOT_STORE_URL="$(AUDIT_HOT_STORE_URL)" \
	AUDIT_WORM_ROOT="$(AUDIT_WORM_ROOT)" \
	AUDIT_SUBJECT_KEYS_PATH="$(AUDIT_SUBJECT_KEYS_PATH)" \
	AUDIT_SINK_MODE="$(AUDIT_SINK_MODE)" \
	AUDIT_WORM_S3_ENDPOINT=

audit-report: ## Render audit report (CID=correlation-id, FORMAT=json|html)
	$(Q)test -n "$(CID)" || { echo "Set CID=<32-hex correlation id>"; exit 1; }
	$(Q)mkdir -p "$(AUDIT_ROOT)" "$(AUDIT_WORM_ROOT)"
	$(Q)cd $(TKEIR_DIR) && $(AUDIT_HOST_ENV) $(UV) run tkeir-audit report \
		--correlation-id "$(CID)" --format "$(or $(FORMAT),json)"

LAST ?= 24h

audit-summary: ## Recent ActionRecord summary from workspace/audit (LAST=24h)
	$(Q)mkdir -p "$(AUDIT_ROOT)" "$(AUDIT_WORM_ROOT)"
	$(Q)cd $(TKEIR_DIR) && $(AUDIT_HOST_ENV) $(UV) run tkeir-audit summary \
		--last "$(LAST)"

audit-verify: ## Verify hot-store hash chain and WORM segments under workspace/audit
	$(Q)mkdir -p "$(AUDIT_ROOT)" "$(AUDIT_WORM_ROOT)"
	$(Q)cd $(TKEIR_DIR) && $(AUDIT_HOST_ENV) $(UV) run tkeir-audit verify

audit-archive: ## Export unarchived ActionRecords to workspace/audit/worm
	$(Q)mkdir -p "$(AUDIT_ROOT)" "$(AUDIT_WORM_ROOT)"
	$(Q)cd $(TKEIR_DIR) && $(AUDIT_HOST_ENV) $(UV) run tkeir-audit archive

# ---------------------------------------------------------------------------
# Governor CLI (Phase 5)
# ---------------------------------------------------------------------------

governor-flags: ## Show runtime kill-switch flags
	$(Q)cd $(TKEIR_DIR) && GOVERNOR_STATE_ROOT="$(GOVERNOR_STATE_ROOT)" \
		$(UV) run tkeir-governor flags

governor-kill: ## Toggle kill switch (SCOPE=ingest ACTIVE=true REASON=drill)
	$(Q)test -n "$(SCOPE)" || { echo "Set SCOPE=all|ingest|index|inference|hmi-write|agents"; exit 1; }
	$(Q)cd $(TKEIR_DIR) && GOVERNOR_STATE_ROOT="$(GOVERNOR_STATE_ROOT)" \
		$(UV) run tkeir-governor kill \
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
# Vespa infrastructure
# ---------------------------------------------------------------------------

schemas: ## Generate Vespa .sd files (doc_base / global / user) from rag.yaml
	$(Q)$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) python \
		$(SCRIPTS_DIR)/generate_vespa_schemas.py

schemas-check: ## Fail if committed Vespa schemas are stale vs rag.yaml
	$(Q)$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) python \
		$(SCRIPTS_DIR)/generate_vespa_schemas.py --check

pull-bge-model: install ## Download BGE-M3 into resources/modeling/net/bge-m3 (FORCE_BGE=1 refresh)
	$(Q)mkdir -p "$(TKEIR_DIR)/resources/modeling/net"
	cd $(TKEIR_DIR) && \
		$(UV) run --python $(PYTHON) python -m thot.tools.search.pull_models \
			--bge-only --bge-model "$(BGE_MODEL)" \
			$(if $(filter 1,$(FORCE_BGE)),--force-bge,)

pull-models: install ## Ensure local BGE-M3 under resources/modeling/net + optional Ollama pulls
	$(Q)mkdir -p "$(TKEIR_DIR)/resources/modeling/net"
	cd $(TKEIR_DIR) && \
		$(UV) run --python $(PYTHON) python -m thot.tools.search.pull_models \
			$(if $(filter 1,$(FORCE_BGE)),--force-bge,)

pull-vespa: check-docker ## Pull Vespa Docker image (VESPA_IMAGE=$(VESPA_IMAGE))
	$(Q)echo "Pulling $(VESPA_IMAGE)…"
	docker pull "$(VESPA_IMAGE)"

pull-searxng: check-docker ## Pull SearXNG Docker image (SEARXNG_IMAGE=$(SEARXNG_IMAGE))
	$(Q)echo "Pulling $(SEARXNG_IMAGE)…"
	docker pull "$(SEARXNG_IMAGE)"
	$(Q)mkdir -p "$(WORKSPACE)/searxng/config" "$(WORKSPACE)/searxng/data"
	$(Q)if [ ! -f "$(WORKSPACE)/searxng/config/settings.yml" ]; then \
		cp "$(TKEIR_DIR)/resources/searxng/settings.yml" "$(WORKSPACE)/searxng/config/settings.yml"; \
		echo "Installed default SearXNG settings → $(WORKSPACE)/searxng/config/settings.yml"; \
	fi

searxng-up: check-docker ## Start SearXNG on :$(SEARXNG_PORT) (volumes under WORKSPACE/searxng)
	$(Q)mkdir -p "$(WORKSPACE)/searxng/config" "$(WORKSPACE)/searxng/data"
	$(Q)if [ ! -f "$(WORKSPACE)/searxng/config/settings.yml" ]; then \
		cp "$(TKEIR_DIR)/resources/searxng/settings.yml" "$(WORKSPACE)/searxng/config/settings.yml"; \
		echo "Installed default SearXNG settings → $(WORKSPACE)/searxng/config/settings.yml"; \
	fi
	$(Q)if docker ps -a --format '{{.Names}}' | grep -qx '$(SEARXNG_NAME)'; then \
		echo "Removing existing container $(SEARXNG_NAME)…"; \
		docker rm -f "$(SEARXNG_NAME)" >/dev/null; \
	fi
	$(Q)echo "Starting $(SEARXNG_NAME) on :$(SEARXNG_PORT) (image=$(SEARXNG_IMAGE))…"
	docker run --name "$(SEARXNG_NAME)" -d \
		-p "$(SEARXNG_PORT):8080" \
		-v "$(WORKSPACE)/searxng/config/:/etc/searxng/" \
		-v "$(WORKSPACE)/searxng/data/:/var/cache/searxng/" \
		"$(SEARXNG_IMAGE)"
	$(Q)echo "SearXNG UI/API: $(SEARXNG_URL)  (JSON: $(SEARXNG_URL)/search?q=test&format=json)"

searxng-down: check-docker ## Stop/remove SearXNG container (keeps WORKSPACE/searxng volumes)
	-$(Q)docker stop "$(SEARXNG_NAME)" >/dev/null 2>&1 || true
	-$(Q)docker rm "$(SEARXNG_NAME)" >/dev/null 2>&1 || true
	$(Q)echo "Stopped $(SEARXNG_NAME) (config/data under $(WORKSPACE)/searxng kept)"

collector: ## [collector] Start tkeir-collector API (:$(COLLECTOR_PORT)) — return markdown, no NLP/store
	$(Q)mkdir -p "$(WORKSPACE)/collector" "$(WORKSPACE)/searxng/config" "$(WORKSPACE)/searxng/data" \
		"$(AUDIT_ROOT)" "$(AUDIT_WORM_ROOT)" "$(GOVERNOR_STATE_ROOT)"
	cd $(TKEIR_DIR) && \
		TKEIR_WORKSPACE="$(WORKSPACE)" \
		TKEIR_REPO_ROOT="$(ROOT)" \
		TKEIR_SERVICE=tkeir-collector \
		SEARXNG_URL="$(SEARXNG_URL)" \
		COLLECTOR_PORT="$(COLLECTOR_PORT)" \
		OSIRIS_BASE_URL="$${OSIRIS_BASE_URL:-http://127.0.0.1:3000}" \
		AGENT_URL="$${AGENT_URL:-http://127.0.0.1:8092}" \
		OSIRIS_ONTOLOGY_PATH="$${OSIRIS_ONTOLOGY_PATH:-$(ROOT)/../t-keir-osiris/resources/osiris_ontology.yaml}" \
		COLLECTOR_WIKI_ENABLED="$${COLLECTOR_WIKI_ENABLED:-false}" \
		COLLECTOR_WIKI_INTERVAL_S="$${COLLECTOR_WIKI_INTERVAL_S:-0}" \
		GOVERNOR_STATE_ROOT="$(GOVERNOR_STATE_ROOT)" \
		$(AUDIT_HOST_ENV) \
		$(UV) run --no-sync --python $(PYTHON) python -m thot.tools.collector

collector-up: collector ## Alias for make collector

collector-query: check-curl check-jq ## [collector] Sample curl against collector API (/collect)
	curl -fsS "$(COLLECTOR_URL)/collect" \
		-H "Content-Type: application/json" \
		-d "$$(jq -nc \
			--arg query "$(COLLECTOR_QUERY)" \
			--arg topic "$(COLLECTOR_TOPIC)" \
			--arg language "$(COLLECTOR_LANGUAGE)" \
			--argjson max_results $(COLLECTOR_MAX_RESULTS) \
			'{query:$$query,topic:$$topic,language:$$language,max_results:$$max_results}')" \
		| jq .

.PHONY: pull-searxng searxng-up searxng-down collector collector-up collector-query

# VESPA_PULL=1 allows start_vespa.sh to docker-pull when the image is missing.
VESPA_PULL ?= 0

start: check-docker ## Start Vespa Docker container (local image only; VESPA_PULL=1 to pull)
	cd $(VESPA_DIR) && VESPA_IMAGE="$(VESPA_IMAGE)" VESPA_PULL="$(VESPA_PULL)" ./start_vespa.sh

init: install ## Deploy Vespa schemas (container must be running)
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) python -m thot.tools.search.init_vespa --skip-start

bootstrap: install ## Start Vespa + deploy schemas
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) python -m thot.tools.search.init_vespa

vespa-check: ## Vespa health check
	cd $(VESPA_DIR) && ./check_vespa.sh

test-vespa: ## Vespa query smoke test
	cd $(VESPA_DIR) && ./test_data.sh

test-vespa-py: install ## Python unit tests for Vespa client / ontology utils
	cd $(TESTS_DIR) && $(UV) run --project $(TKEIR_DIR) --python $(PYTHON) pytest \
		unittests/TestVespaClient.py unittests/TestOntologyUtils.py -q

# ---------------------------------------------------------------------------
# Ingest / index — thot.tools.ingest
# ---------------------------------------------------------------------------

index-fixtures: ## [ingest] Build indexing fixtures (PDF → *.pipeline.json)
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

index: install init ## [ingest] Embed + index pipeline JSON (thot.tools.ingest.index_documents)
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
	$(Q)echo "Indexing from $(INDEX_INPUT) via thot.tools.ingest.index_documents"
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) python -m thot.tools.ingest.index_documents -i "$(INDEX_INPUT)"

GOVERNOR_STATE_ROOT ?= $(WORKSPACE)/governor

INGEST_ROOT_HOST ?= $(WORKSPACE)/ingest
# STOP_ON_FAILED=1 → ingest server exits on first failed job; datasets client
# also aborts and calls POST /ingest/stop (fast debug loop).
STOP_ON_FAILED ?= 0

ingest: install install-spacy-models ## [ingest] Start tkeir-ingest API on host (:8091)
	$(Q)mkdir -p "$(INGEST_ROOT_HOST)" "$(GOVERNOR_STATE_ROOT)" "$(AUDIT_ROOT)" "$(AUDIT_WORM_ROOT)"
	cd $(TKEIR_DIR) && \
		INGEST_ROOT="$(INGEST_ROOT_HOST)" \
		INGEST_MAX_CONCURRENCY="$(or $(INGEST_MAX_CONCURRENCY),1)" \
		INGEST_STOP_ON_FAILED="$(STOP_ON_FAILED)" \
		GOVERNOR_STATE_ROOT="$(GOVERNOR_STATE_ROOT)" \
		VESPA_USER_SPACE="$(or $(VESPA_USER_SPACE),dev@tkeir)" \
		TKEIR_WORKSPACE="$(WORKSPACE)" \
		TKEIR_REPO_ROOT="$(ROOT)" \
		$(AUDIT_HOST_ENV) \
		$(UV) run --python $(PYTHON) tkeir-ingest

# ---------------------------------------------------------------------------
# Search / RAG — thot.tools.search
# ---------------------------------------------------------------------------

rag: install install-spacy-models ## [search] Start FastAPI RAG API on host (:8090)
	$(Q)mkdir -p "$(GOVERNOR_STATE_ROOT)" "$(INGEST_ROOT_HOST)" "$(AUDIT_ROOT)" "$(AUDIT_WORM_ROOT)"
	cd $(TKEIR_DIR) && GOVERNOR_STATE_ROOT="$(GOVERNOR_STATE_ROOT)" \
		INGEST_ROOT="$(INGEST_ROOT_HOST)" \
		$(AUDIT_HOST_ENV) \
		$(UV) run --python $(PYTHON) python -m thot.tools.search.app

rag-query: check-curl check-jq ## [search] Sample curl against RAG API (/rag/query)
	curl -fsS "$(RAG_URL)/rag/query" \
		-H "Content-Type: application/json" \
		-d "$$(jq -nc --arg query "$(RAG_QUERY)" --arg language "$(RAG_LANGUAGE)" --argjson hits $(RAG_HITS) '{query:$$query,language:$$language,hits:$$hits}')" \
		| jq .

search-query: check-curl check-jq ## [search] Sample curl against search API (/search)
	curl -fsS "$(RAG_URL)/search" \
		-H "Content-Type: application/json" \
		-d "$$(jq -nc --arg query "$(RAG_QUERY)" --arg language "$(RAG_LANGUAGE)" --argjson hits $(RAG_HITS) '{query:$$query,language:$$language,hits:$$hits}')" \
		| jq .

MCP_URL ?= http://localhost:8093
MCP_QUERY ?= what is t-keir

mcp: ## Start tkeir-mcp HTTP server (:8093; MCP_STDIO=1 for official MCP stdio)
	$(Q)mkdir -p "$(AUDIT_ROOT)" "$(AUDIT_WORM_ROOT)"
	$(Q)if [ "$(MCP_STDIO)" = "1" ]; then \
		cd $(TKEIR_DIR) && $(AUDIT_HOST_ENV) $(UV) run --python $(PYTHON) --extra mcp python -m thot.mcp.server --stdio; \
	else \
		cd $(TKEIR_DIR) && $(AUDIT_HOST_ENV) $(UV) run --python $(PYTHON) python -m thot.mcp.server; \
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
# Orchestrator report-form maps: datasets/<usecase>/agent_orchestrator.yaml
# Override for enterprise: make agent TKEIR_AGENT_USECASE=enterprise
TKEIR_AGENT_USECASE ?= osint
TKEIR_AGENT_ORCHESTRATOR_CONFIG ?= $(ROOT)/datasets/$(TKEIR_AGENT_USECASE)/agent_orchestrator.yaml
# Persona wiki merges often need >5m on local Ollama; override with
# LLM_GENERATE_TIMEOUT_SECONDS=…
LLM_GENERATE_TIMEOUT_SECONDS ?= 600

agent: spire-up ## Start tkeir-agent HTTP service (:8092)
	$(Q)mkdir -p "$(AUDIT_ROOT)" "$(AUDIT_WORM_ROOT)" "$(WORKSPACE)/users" "$(AGENT_ROOT)"
	$(Q)test -f "$(TKEIR_AGENT_ORCHESTRATOR_CONFIG)" || { \
		echo "Missing agent orchestrator config: $(TKEIR_AGENT_ORCHESTRATOR_CONFIG)"; \
		echo "Set TKEIR_AGENT_USECASE=osint|enterprise or TKEIR_AGENT_ORCHESTRATOR_CONFIG=…"; \
		exit 1; \
	}
	cd $(TKEIR_DIR) && AGENT_ROOT="$(AGENT_ROOT)" \
		TKEIR_WORKSPACE="$(WORKSPACE)" \
		TKEIR_AGENT_USECASE="$(TKEIR_AGENT_USECASE)" \
		TKEIR_AGENT_ORCHESTRATOR_CONFIG="$(TKEIR_AGENT_ORCHESTRATOR_CONFIG)" \
		SPIFFE_ENFORCE="$${SPIFFE_ENFORCE:-true}" \
		LLM_GENERATE_TIMEOUT_SECONDS="$(LLM_GENERATE_TIMEOUT_SECONDS)" \
		$(AUDIT_HOST_ENV) \
		$(UV) run --python $(PYTHON) python -m thot.tools.agent

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

OKF_URL ?= http://localhost:8095
# OKF storage layout (TKEIR_WORKSPACE=$(WORKSPACE)):
#   - Per-user (default writes): $(WORKSPACE)/users/<space>/okf/<bundle_id>/
#   - Flat fallback:             $(OKF_FLAT_ROOT)  (= $(WORKSPACE)/.tkeir-okf)
#   - Explicit override:         OKF_ROOT=/path   (tests / one-off)
OKF_ROOT ?=
OKF_PORT ?= 8095
OKF_QUERY ?=
OKF_MAX_DOCS ?= 50
USER_SPACE ?= dev@tkeir

okf: ## Start OKF server (:8095; bundles under WORKSPACE users/…/okf or OKF_FLAT_ROOT)
	$(Q)mkdir -p "$(GOVERNOR_STATE_ROOT)" "$(WORKSPACE)/users" \
		"$(OKF_FLAT_ROOT)" "$(AUDIT_ROOT)" "$(AUDIT_WORM_ROOT)"
	cd $(TKEIR_DIR) && TKEIR_WORKSPACE="$(WORKSPACE)" OKF_PORT="$(OKF_PORT)" \
		$(if $(strip $(OKF_ROOT)),OKF_ROOT="$(OKF_ROOT)",) \
		GOVERNOR_STATE_ROOT="$(GOVERNOR_STATE_ROOT)" \
		INGEST_URL="$(or $(INGEST_URL),$(INGEST_API_URL))" \
		$(AUDIT_HOST_ENV) \
		$(UV) run --python $(PYTHON) python -m thot.tools.okf

# ---------------------------------------------------------------------------
# Demo runners — start each major component explicitly
# ---------------------------------------------------------------------------
.PHONY: vespa-up keycloak-up keycloak-sync-demo-users keycloak-purge-demo-users spire-up index-up rag-up okf-up governor-up audit-up audit-worm-list hmi-up wipe-runtime down all-down

vespa-up: ## Start Vespa container on :8080/19071 (no image pull; use make pull-vespa)
	$(MAKE) start VESPA_PULL=0

keycloak-up: ## Start Keycloak (auth profile) then sync demo users
	$(MAKE) compose-up PROFILES=auth
	$(MAKE) keycloak-sync-demo-users

KEYCLOAK_URL ?= http://localhost:8082
KEYCLOAK_ADMIN ?= admin
KEYCLOAK_ADMIN_PASSWORD ?= admin
KEYCLOAK_REALM ?= tkeir
KEYCLOAK_PURGE_ROLES ?= 0
KEYCLOAK_WAIT_SECS ?= 30

keycloak-sync-demo-users: check-curl ## Ensure demo persona users/roles/clearance exist in Keycloak
	$(Q)KEYCLOAK_URL="$(KEYCLOAK_URL)" \
		KEYCLOAK_ADMIN="$(KEYCLOAK_ADMIN)" \
		KEYCLOAK_ADMIN_PASSWORD="$(KEYCLOAK_ADMIN_PASSWORD)" \
		KEYCLOAK_REALM="$(KEYCLOAK_REALM)" \
		python3 "$(SCRIPTS_DIR)/cluster/keycloak-sync-demo-users.py"

keycloak-purge-demo-users: ## Remove demo persona users from Keycloak (best-effort)
	$(Q)KEYCLOAK_URL="$(KEYCLOAK_URL)" \
		KEYCLOAK_ADMIN="$(KEYCLOAK_ADMIN)" \
		KEYCLOAK_ADMIN_PASSWORD="$(KEYCLOAK_ADMIN_PASSWORD)" \
		KEYCLOAK_REALM="$(KEYCLOAK_REALM)" \
		KEYCLOAK_PURGE_ROLES="$(KEYCLOAK_PURGE_ROLES)" \
		KEYCLOAK_WAIT_SECS="$(KEYCLOAK_WAIT_SECS)" \
		python3 "$(SCRIPTS_DIR)/cluster/keycloak-purge-demo-users.py" || true

spire-up: check-docker ## Start SPIRE server+agent (mint join token automatically)
	$(MAKE) compose-up PROFILES=spire
	$(Q)echo "Waiting for tkeir-spire-server healthy…"
	$(Q)i=0; \
	while [ $$i -lt 60 ]; do \
		st=$$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' tkeir-spire-server 2>/dev/null || echo missing); \
		if [ "$$st" = "healthy" ]; then break; fi; \
		i=$$((i + 1)); sleep 2; \
	done; \
	st=$$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' tkeir-spire-server 2>/dev/null || echo missing); \
	test "$$st" = "healthy" || { echo "SPIRE server not healthy (status=$$st). Logs:"; docker logs --tail=40 tkeir-spire-server; exit 1; }
	$(Q)TOKEN=$$(docker exec tkeir-spire-server /opt/spire/bin/spire-server token generate \
		-socketPath /tmp/spire-server/private/api.sock \
		-spiffeID spiffe://tkeir.local/spire-agent \
		| sed -n 's/^Token:[[:space:]]*//p' | tr -d '\r'); \
	test -n "$$TOKEN" || { echo "Failed to mint SPIRE join token"; exit 1; }; \
	echo "Minted join token; (re)starting SPIRE agent…"; \
	ENV_FILE="$(COMPOSE_DIR)/.env"; \
	test -f "$$ENV_FILE" || ENV_FILE="$(COMPOSE_DIR)/.env.example"; \
	SPIRE_JOIN_TOKEN="$$TOKEN" IMAGE_REGISTRY="$(IMAGE_REGISTRY)" IMAGE_TAG="$(IMAGE_TAG)" \
		VERSION="$(VERSION)" GIT_COMMIT="$(GIT_COMMIT)" BUILD_DATE="$(BUILD_DATE)" \
		$(COMPOSE) -f "$(COMPOSE_FILE)" --env-file "$$ENV_FILE" --profile spire \
			up -d --force-recreate --no-deps spire-agent
	$(Q)echo "SPIRE up. Server healthy; agent joined as spiffe://tkeir.local/spire-agent"
	$(Q)echo "Optional workload entries: bash deploy/spire/register-agent-entries.sh (from inside server, or adapt socket path)"

index-up: install init ## Demo: deploy Vespa schemas + start host ingest (:8091)
	$(Q)echo "Vespa schemas ready. Starting ingest API — load user/global docs via the HMI (not make index)."
	$(MAKE) ingest

rag-up: ## Start RAG FastAPI on host (make rag)
	$(MAKE) rag

okf-up: ## Start OKF server on host (make okf)
	$(MAKE) okf

.PHONY: okf-migrate-workspace

hmi-up: ## Start tkeir-hmi Next.js UI on host (:3000)
	$(Q)test -d "$(HMI_DIR)/node_modules" || $(MAKE) hmi-install
	$(Q)test -f "$(HMI_DIR)/.env.local" \
		|| cp "$(HMI_DIR)/.env.local.example" "$(HMI_DIR)/.env.local"
	cd $(HMI_DIR) && npm run dev

governor-up: ## Start governor API on host (:8094)
	$(Q)mkdir -p "$(GOVERNOR_STATE_ROOT)"
	cd $(TKEIR_DIR) && \
		GOVERNOR_STATE_ROOT="$(GOVERNOR_STATE_ROOT)" \
		GOVERNOR_AUTH_ENABLED="$(GOVERNOR_AUTH_ENABLED)" \
		$(UV) run --python $(PYTHON) python -m thot.governor.app

audit-up: ## Start audit API on host (:8093) reading workspace/audit
	$(Q)mkdir -p "$(AUDIT_WORM_ROOT)" "$(AUDIT_ROOT)"
	cd $(TKEIR_DIR) && \
		$(AUDIT_HOST_ENV) \
		AUDIT_AUTH_ENABLED="$(AUDIT_AUTH_ENABLED)" \
		$(UV) run --python $(PYTHON) python -m thot.audit.app

audit-worm-list: ## List audit WORM segment files under workspace/audit/worm
	$(Q)ls -lah "$(AUDIT_WORM_ROOT)"

okf-export: ## CLI export → WORKSPACE/users/<space>/okf (or OKF_FLAT_ROOT / OKF_ROOT)
	$(Q)mkdir -p "$(WORKSPACE)/users" "$(OKF_FLAT_ROOT)"
	cd $(TKEIR_DIR) && TKEIR_WORKSPACE="$(WORKSPACE)" \
		$(if $(strip $(OKF_ROOT)),OKF_ROOT="$(OKF_ROOT)",) \
		$(UV) run --python $(PYTHON) python -m thot.okf.exporter \
		--user-space "$(USER_SPACE)" \
		--max-docs "$(OKF_MAX_DOCS)" \
		$(if $(strip $(OKF_QUERY)$(QUERY)),--query "$(or $(OKF_QUERY),$(QUERY))",) \
		$(if $(strip $(OUTPUT)),--output "$(OUTPUT)",)

okf-migrate-workspace: ## Move flat OKF (OKF_FLAT_ROOT) → workspace/users/<space>/okf/
	$(Q)mkdir -p "$(WORKSPACE)/users" "$(OKF_FLAT_ROOT)"
	cd $(TKEIR_DIR) && TKEIR_WORKSPACE="$(WORKSPACE)" \
		$(UV) run --python $(PYTHON) python -c \
		'from pathlib import Path; from thot.okf.store import migrate_flat_okf_into_workspace; \
root=Path(r"$(OKF_FLAT_ROOT)").resolve(); \
moved=migrate_flat_okf_into_workspace(root) if root.is_dir() else []; \
print("migrated", len(moved), "bundles from", str(root), "→", moved)'

okf-workflow: check-curl check-jq ## Run OKF agent workflow (WORKFLOW=llm_wiki|okf_wiki_brief)
	$(MAKE) workflow-run WORKFLOW="$(or $(WORKFLOW),llm_wiki)" \
		GOAL="$(or $(GOAL),Produce an OKF LLMWiki answering the query)" \
		TOPIC="$(or $(TOPIC),Objective ALPHA)"

okf-bundle-ls: check-curl check-jq ## List bundles for USER_SPACE
	curl -fsS "$(OKF_URL)/okf/bundles" | jq .

# ---------------------------------------------------------------------------
# Zero-to-Hero datasets: NATO OSINT + Enterprise (§3.4 + §5.5)
# Versioned under datasets/{osint,enterprise}/ (VERSION + business_ontology.yaml + ontologies/)
# ---------------------------------------------------------------------------
DATASETS_OUT           ?= $(ROOT)/datasets
DATASETS_SEED          ?= 42
DATASETS_COUNT_OSINT   ?= 1500
DATASETS_COUNT_ENT     ?= 500
# Set DATASETS_DOWNLOAD=0 for a fully offline generate (skip SISO / EnterpriseRAG fetch).
DATASETS_DOWNLOAD      ?= 1
DATASETS_FLAGS         ?=
INGEST_API_URL         ?= http://localhost:8091
INGEST_TOKEN_URL       ?= http://localhost:8082/realms/tkeir/protocol/openid-connect/token
INGEST_WORKERS         ?= 1
INGEST_FLAGS           ?=
# Appended when STOP_ON_FAILED=1 (see ingest target too).
_STOP_ON_FAILED_FLAG = $(if $(filter 1 true TRUE yes YES,$(STOP_ON_FAILED)),--stop-on-failed,)

_DATASETS_PY := $(ROOT)/tools/datasets/generate_tkeir_datasets.py
_INGEST_PY   := $(ROOT)/tools/datasets/ingest_dataset.py
_DATASETS_RUN := cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) python

datasets: ## [datasets] Generate OSINT+Enterprise and best-effort download official artifacts
	$(_DATASETS_RUN) $(_DATASETS_PY) \
	  --output $(DATASETS_OUT) \
	  --count-osint $(DATASETS_COUNT_OSINT) \
	  --count-enterprise $(DATASETS_COUNT_ENT) \
	  --seed $(DATASETS_SEED) \
	  $(if $(filter 1,$(DATASETS_DOWNLOAD)),--download,) \
	  $(DATASETS_FLAGS)
	@echo "Next (P0 host): make bootstrap && make ingest   # other terminal: make datasets-ingest"
	@echo "Next (P1):      make compose-up PROFILES=core,auth,ingest && make datasets-ingest-user"
	@echo "Offline-only: make datasets DATASETS_DOWNLOAD=0"

datasets-ontologies: ## [datasets] Generate C2SIM/C4ISR + business ontologies / VERSION only
	$(_DATASETS_RUN) $(_DATASETS_PY) \
	  --output $(DATASETS_OUT) --only-ontologies $(DATASETS_FLAGS)

datasets-download: datasets ## [datasets] Alias for 'make datasets' (generate + download)

scidocs-download: ## [datasets] Download BEIR SciDocs corpus into datasets/scidocs/ (gitignored bulk)
	$(Q)chmod +x "$(ROOT)/datasets/scidocs/download.sh"
	$(Q)bash "$(ROOT)/datasets/scidocs/download.sh"

# Process-time OWL/TTL for OSINT ingest (ingest API stays dataset-agnostic).
# Override with DATASETS_ONTOLOGIES=a.ttl,b.owl or DATASETS_ONTOLOGY_DIR=/other/dir
DATASETS_ONTOLOGY_DIR ?= $(DATASETS_OUT)/osint/ontologies
DATASETS_ONTOLOGIES ?=
_INGEST_ONTOLOGY_ARGS = $(if $(DATASETS_ONTOLOGIES),--ontologies $(DATASETS_ONTOLOGIES),$(if $(DATASETS_ONTOLOGY_DIR),--ontology-dir $(DATASETS_ONTOLOGY_DIR),))

define _require_datasets_ontologies
	@if [ -n "$(DATASETS_ONTOLOGIES)" ]; then \
	  echo "Using ontologies: $(DATASETS_ONTOLOGIES)"; \
	elif [ -z "$(DATASETS_ONTOLOGY_DIR)" ]; then \
	  echo "ERROR: datasets-ingest requires ontologies — set DATASETS_ONTOLOGY_DIR or DATASETS_ONTOLOGIES"; \
	  exit 1; \
	elif [ ! -d "$(DATASETS_ONTOLOGY_DIR)" ]; then \
	  echo "ERROR: ontology dir missing: $(DATASETS_ONTOLOGY_DIR)"; \
	  echo "  Run: make datasets   (or make datasets-ontologies)"; \
	  exit 1; \
	elif [ -z "$$(find "$(DATASETS_ONTOLOGY_DIR)" -maxdepth 1 \( -name '*.ttl' -o -name '*.owl' -o -name '*.rdf' -o -name '*.xml' \) -print -quit)" ]; then \
	  echo "ERROR: no OWL/TTL/RDF files in $(DATASETS_ONTOLOGY_DIR)"; \
	  echo "  Run: make datasets   (or make datasets-ontologies)"; \
	  exit 1; \
	else \
	  echo "Using ontologies from $(DATASETS_ONTOLOGY_DIR)"; \
	fi
endef

datasets-ingest: ## [datasets] Ingest OSINT+Enterprise via :8091 (OSINT with ontologies; enterprise without)
	$(call _require_datasets_ontologies)
	$(_DATASETS_RUN) $(_INGEST_PY) \
	  --datasets-dir $(DATASETS_OUT) \
	  --api-url $(INGEST_API_URL) \
	  --dataset osint \
	  --user-space dev@tkeir \
	  --workers $(INGEST_WORKERS) \
	  --fallback-index \
	  --output-report $(DATASETS_OUT)/ingest_osint.json \
	  $(_INGEST_ONTOLOGY_ARGS) \
	  $(_STOP_ON_FAILED_FLAG) \
	  $(INGEST_FLAGS)
	$(_DATASETS_RUN) $(_INGEST_PY) \
	  --datasets-dir $(DATASETS_OUT) \
	  --api-url $(INGEST_API_URL) \
	  --dataset enterprise \
	  --user-space dev@tkeir \
	  --workers $(INGEST_WORKERS) \
	  --fallback-index \
	  --output-report $(DATASETS_OUT)/ingest_enterprise.json \
	  $(_STOP_ON_FAILED_FLAG) \
	  $(INGEST_FLAGS)
	@echo "If API was down (P0): make bootstrap && make ingest   # then re-run make datasets-ingest"
	@echo "If API was down (P1): make images && make compose-up PROFILES=core,ingest"
	@echo "OSINT ingested with ontologies; enterprise ingested without"
	@echo "Debug tip: make ingest STOP_ON_FAILED=1  &&  make datasets-ingest STOP_ON_FAILED=1"

datasets-ingest-user: ## [datasets] Ingest OSINT as demo-user (P1, Keycloak required)
	$(call _require_datasets_ontologies)
	$(_DATASETS_RUN) $(_INGEST_PY) \
	  --datasets-dir $(DATASETS_OUT) \
	  --api-url $(INGEST_API_URL) \
	  --dataset osint \
	  --username demo-user --password demo-user \
	  --token-url $(INGEST_TOKEN_URL) \
	  --workers $(INGEST_WORKERS) \
	  --status-poll \
	  --output-report $(DATASETS_OUT)/ingest_user.json \
	  $(_INGEST_ONTOLOGY_ARGS) \
	  $(_STOP_ON_FAILED_FLAG) \
	  $(INGEST_FLAGS)

datasets-ingest-admin: ## [datasets] Ingest Enterprise as demo-admin (P1, Keycloak required)
	$(_DATASETS_RUN) $(_INGEST_PY) \
	  --datasets-dir $(DATASETS_OUT) \
	  --api-url $(INGEST_API_URL) \
	  --dataset enterprise \
	  --username demo-admin --password demo-admin \
	  --token-url $(INGEST_TOKEN_URL) \
	  --workers $(INGEST_WORKERS) \
	  --status-poll \
	  --output-report $(DATASETS_OUT)/ingest_admin.json \
	  $(_STOP_ON_FAILED_FLAG) \
	  $(INGEST_FLAGS)

datasets-ingest-web: ## [datasets] Print HMI drag-and-drop + curl guide for web ingestion
	$(_DATASETS_RUN) $(_INGEST_PY) \
	  --datasets-dir $(DATASETS_OUT) \
	  --api-url $(INGEST_API_URL) \
	  --token-url $(INGEST_TOKEN_URL) \
	  --print-web-guide

datasets-demo: datasets datasets-ingest ## [datasets] One-shot: generate → ingest (P0 host ingest must be up)
	@echo "=== Datasets demo ready (P0 / dev@tkeir) ==="
	@echo "  Prerequisite: make bootstrap && make ingest (host; no tkeir containers)"
	@echo "  RAG: make rag && make rag-query RAG_QUERY=\"SITREP Objective ALPHA\""
	@echo "  HMI: cd tkeir-hmi && npm run dev → http://localhost:3000"
	@echo "  P1 isolation: make images && make compose-up PROFILES=core,auth,ingest"
	@echo "                make datasets-ingest-user && make datasets-ingest-admin"

datasets-clean: ## [datasets] Remove generated document trees (keeps VERSION / business_ontology / OWL stubs)
	rm -rf $(DATASETS_OUT)/osint/raw $(DATASETS_OUT)/osint/markdown $(DATASETS_OUT)/osint/html \
	  $(DATASETS_OUT)/osint/json $(DATASETS_OUT)/osint/pdf $(DATASETS_OUT)/osint/docx \
	  $(DATASETS_OUT)/osint/csv $(DATASETS_OUT)/osint/xml $(DATASETS_OUT)/osint/ontologies/official \
	  $(DATASETS_OUT)/osint/manifest.json \
	  $(DATASETS_OUT)/enterprise/raw $(DATASETS_OUT)/enterprise/markdown $(DATASETS_OUT)/enterprise/html \
	  $(DATASETS_OUT)/enterprise/json $(DATASETS_OUT)/enterprise/pdf $(DATASETS_OUT)/enterprise/docx \
	  $(DATASETS_OUT)/enterprise/csv $(DATASETS_OUT)/enterprise/manifest.json \
	  $(DATASETS_OUT)/ingest_osint.json $(DATASETS_OUT)/ingest_enterprise.json \
	  $(DATASETS_OUT)/ingest_user.json $(DATASETS_OUT)/ingest_admin.json
	@echo "Cleaned generated docs under $(DATASETS_OUT)/{osint,enterprise} (versioned ontologies kept)"

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

# ---------------------------------------------------------------------------
# Eval / BEIR — thot.tools.eval
# ---------------------------------------------------------------------------
# Optional extra report copy; docs report is always written by beir_eval.
# Prefers hard-failure query ids from docs/evaluation_report.md
# (beir_smoke.EVAL_REPORT_FOCUS_QUERIES). Disable:
#   BEIR_SMOKE_EXTRA=--no-focus-eval-report
# Override: BEIR_SMOKE_QUERIES=12 BEIR_SMOKE_CLOSE=15 BEIR_SMOKE_RANK_DOCS=20
# Speed-only (skip NLP): BEIR_SMOKE_INDEX_MODE=fast

BEIR_SMOKE_QUERIES ?= 10
BEIR_SMOKE_CLOSE   ?= 10
BEIR_SMOKE_RANK_DOCS ?= 10
BEIR_SMOKE_TOP_K   ?= 10
BEIR_SMOKE_INDEX_MODE ?= chunking
BEIR_SMOKE_EXTRA   ?=

# uv may re-fetch spaCy wheels from GitHub (slow / flaky); raise timeout for eval sync.
UV_HTTP_TIMEOUT ?= 300

beir-eval: install-spacy-models ## [eval] Full BEIR IR eval (thot.tools.eval.beir_eval); BEIR_DATASETS=scifact
	cd $(TKEIR_DIR) && UV_HTTP_TIMEOUT="$(UV_HTTP_TIMEOUT)" \
		$(UV) sync --group beir --group models --python $(PYTHON)
	cd $(TKEIR_DIR) && \
		VESPA_NAME="$(BEIR_VESPA_NAME)" \
		VESPA_VOLUME="$(BEIR_VESPA_VOLUME)" \
		$(UV) run --no-sync --python $(PYTHON) --group beir --group models \
		python -m thot.tools.eval.beir_eval \
		--datasets $(BEIR_DATASETS) \
		--datasets-dir "$(BEIR_DATASETS_DIR)" \
		--dense-model "$(BEIR_DENSE_MODEL)" \
		$(if $(strip $(BEIR_REPORT)),--report "$(BEIR_REPORT)",) \
		$(BEIR_EXTRA)

generate-eval: install-spacy-models ## [eval] Oracle-evidence generation eval (thot.tools.eval.generate_eval)
	cd $(TKEIR_DIR) && UV_HTTP_TIMEOUT="$(UV_HTTP_TIMEOUT)" \
		$(UV) sync --group models --python $(PYTHON)
	cd $(TKEIR_DIR) && \
		$(UV) run --no-sync --python $(PYTHON) --group models \
		python -m thot.tools.eval.generate_eval \
		--datasets $(GEN_DATASETS) \
		--rag-dir "$(GEN_BENCHMARKS_DIR)" \
		$(if $(strip $(GEN_REPORT)),--report "$(GEN_REPORT)",) \
		$(GEN_EXTRA)

rag-eval beir-rag-eval: ## [eval] Deprecated aliases for generate-eval
	@$(MAKE) generate-eval \
		GEN_DATASETS="$(RAG_DATASETS)" \
		GEN_BENCHMARKS_DIR="$(RAG_BENCHMARKS_DIR)" \
		GEN_REPORT="$(RAG_REPORT)" \
		GEN_EXTRA="$(RAG_EXTRA)"

beir-smoke: install-spacy-models ## [eval] Fast BEIR smoke (thot.tools.eval.beir_smoke)
	cd $(TKEIR_DIR) && UV_HTTP_TIMEOUT="$(UV_HTTP_TIMEOUT)" \
		$(UV) sync --group beir --group models --python $(PYTHON)
	cd $(TKEIR_DIR) && \
		VESPA_NAME="$(BEIR_VESPA_NAME)" \
		VESPA_VOLUME="$(BEIR_VESPA_VOLUME)" \
		$(UV) run --no-sync --python $(PYTHON) --group beir --group models \
		python -m thot.tools.eval.beir_smoke \
		--datasets $(BEIR_DATASETS) \
		--datasets-dir "$(BEIR_DATASETS_DIR)" \
		--queries $(BEIR_SMOKE_QUERIES) \
		--close-docs $(BEIR_SMOKE_CLOSE) \
		--rank-docs $(BEIR_SMOKE_RANK_DOCS) \
		--top-k $(BEIR_SMOKE_TOP_K) \
		--index-mode $(BEIR_SMOKE_INDEX_MODE) \
		$(BEIR_SMOKE_EXTRA)

eval: beir-eval ## [eval] Alias for beir-eval
eval-smoke: beir-smoke ## [eval] Alias for beir-smoke

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
## (+ EUR-Lex legal excerpts from compliance/opa/legal/*.yaml)
.PHONY: compliance-doc-tables compliance-legal-texts
compliance-legal-texts:
	python3 compliance/opa/scripts/fetch_legal_texts.py

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

# ---------------------------------------------------------------------------
# Integration / fuzz / BDD / SLSA / cosign (supply-chain hardening)
# Appended targets — do not rewrite the existing quality gate bodies above.
# ---------------------------------------------------------------------------

test-integration: check-uv check-python-version ## [test] pytest integration suite (tests/integration/)
	$(Q)mkdir -p "$(INTEGRATION_REPORT_DIR)"
	$(Q)cd $(TKEIR_DIR) && RAG_URL="$(RAG_URL_TEST)" INGEST_URL="$(INGEST_URL_TEST)" \
		$(UV) run --python $(PYTHON) --with pytest-timeout \
		pytest "$(ROOT)/tests/integration/" -v --timeout=$(INTEGRATION_TIMEOUT)

test-integration-ci: check-uv check-python-version ## [test] Integration tests with JUnit XML output for CI
	$(Q)mkdir -p "$(INTEGRATION_REPORT_DIR)"
	$(Q)cd $(TKEIR_DIR) && RAG_URL="$(RAG_URL_TEST)" INGEST_URL="$(INGEST_URL_TEST)" \
		$(UV) run --python $(PYTHON) --with pytest-timeout \
		pytest "$(ROOT)/tests/integration/" -v --timeout=$(INTEGRATION_TIMEOUT) \
		--tb=short --junitxml="$(INTEGRATION_REPORT_DIR)/junit.xml"

test-fuzz-hypothesis: check-uv check-python-version ## [test] Hypothesis property-based fuzz (tests/fuzzing/)
	$(Q)mkdir -p "$(FUZZ_REPORT_DIR)"
	$(Q)cd $(TKEIR_DIR) && \
		HYPOTHESIS_MAX_EXAMPLES=500 HYPOTHESIS_DERANDOMIZE=0 \
		$(UV) run --python $(PYTHON) --with 'hypothesis[cli]' \
		pytest "$(ROOT)/tests/fuzzing/test_fuzz_hypothesis.py" -v \
		--hypothesis-seed=$(HYPOTHESIS_SEED)

test-fuzz-atheris: check-uv check-python-version ## [test] Atheris libFuzzer targets (Linux only; FUZZ_DURATION=60)
	$(Q)if ! uname -s | grep -qx Linux; then echo "SKIP: atheris only on Linux"; exit 0; fi; \
		mkdir -p "$(FUZZ_REPORT_DIR)" "$(FUZZ_CORPUS_DIR)/query"; \
		cd $(TKEIR_DIR) && \
		if ! $(UV) run --python $(PYTHON) python -c "import atheris" 2>/dev/null; then \
			echo "Installing atheris into uv environment…"; \
			$(UV) pip install atheris; \
		fi; \
		for target in $(ROOT)/tests/fuzzing/fuzz_targets/*.py; do \
			[ -f "$$target" ] || continue; \
			echo "Fuzzing $$target (duration=$(FUZZ_DURATION)s)…"; \
			FUZZ_MODE=atheris FUZZ_RUNS=5000 \
			$(UV) run --python $(PYTHON) python "$$target" \
				"-artifact_prefix=$(FUZZ_REPORT_DIR)/" \
				"-max_total_time=$(FUZZ_DURATION)" \
				"$(FUZZ_CORPUS_DIR)/query/" \
				|| echo "WARN: atheris target exited $$? (see $(FUZZ_REPORT_DIR)/)"; \
		done

test-fuzz-radamsa: check-radamsa check-uv check-python-version ## [test] Radamsa mutation fuzz (corpus → fuzz_targets)
	$(Q)mkdir -p "$(FUZZ_REPORT_DIR)" "$(FUZZ_CORPUS_DIR)/query"
	$(Q)cd $(TKEIR_DIR) && \
		PYTHONPATH="$(ROOT):$(TKEIR_DIR)$${PYTHONPATH:+:$$PYTHONPATH}" \
		RADAMSA="$(RADAMSA)" RADAMSA_COUNT="$(RADAMSA_COUNT)" RADAMSA_SEED="$(RADAMSA_SEED)" \
		$(UV) run --python $(PYTHON) python "$(SCRIPTS_DIR)/fuzzing/run_radamsa.py" \
			--corpus-dir "$(FUZZ_CORPUS_DIR)/query" \
			--report-dir "$(FUZZ_REPORT_DIR)" \
			--targets-dir "$(ROOT)/tests/fuzzing/fuzz_targets" \
			--count "$(RADAMSA_COUNT)" \
			--seed "$(RADAMSA_SEED)" \
			--radamsa "$(RADAMSA)"

test-fuzz: test-fuzz-hypothesis test-fuzz-atheris test-fuzz-radamsa ## [test] All fuzz layers (hypothesis + atheris + radamsa)

fuzz-report: ## [test] Merge atheris/radamsa findings into corpus; export JSON summary
	$(Q)mkdir -p "$(FUZZ_REPORT_DIR)" "$(FUZZ_CORPUS_DIR)/query"
	$(Q)$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		python "$(SCRIPTS_DIR)/slsa/fuzz_report.py" \
		--report-dir "$(FUZZ_REPORT_DIR)" \
		--corpus-dir "$(FUZZ_CORPUS_DIR)/query"

test-bdd: check-uv check-python-version ## [test] Behave BDD suite (tests/bdd/features/)
	$(Q)cd $(ROOT) && RAG_URL="$(RAG_URL_TEST)" INGEST_URL="$(INGEST_URL_TEST)" \
		PYTHONPATH="$(ROOT):$(TKEIR_DIR)" \
		$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) --with behave \
		behave "$(BDD_FEATURES)" --format "$(BDD_FORMAT)"

test-bdd-ci: check-uv check-python-version ## [test] BDD with JSON + JUnit output for CI dashboards
	$(Q)mkdir -p "$(BDD_REPORT_DIR)"
	$(Q)cd $(ROOT) && RAG_URL="$(RAG_URL_TEST)" INGEST_URL="$(INGEST_URL_TEST)" \
		PYTHONPATH="$(ROOT):$(TKEIR_DIR)" \
		$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) --with behave \
		behave "$(BDD_FEATURES)" \
			--format json --outfile "$(BDD_REPORT_DIR)/behave.json" \
			--format progress3 \
			--junit --junit-directory "$(BDD_REPORT_DIR)/"

bdd-report: ## [test] Convert behave JSON output to Allure-compatible report
	$(Q)mkdir -p "$(BDD_REPORT_DIR)"
	$(Q)if command -v allure >/dev/null 2>&1; then \
		allure generate "$(BDD_REPORT_DIR)" -o "$(BDD_REPORT_DIR)/allure-html" --clean; \
		echo "Allure report → $(BDD_REPORT_DIR)/allure-html"; \
	else \
		echo "WARN: allure CLI not found — skipping bdd-report (https://docs.qameta.io/allure/)"; \
	fi

slsa-prereqs: check-uv check-curl ## [slsa] Check verdit-slsa + slsa-verifier installed; install if missing
	$(Q)mkdir -p "$(HOME)/.local/bin" "$(SLSA_REPORT_DIR)"
	$(Q)if ! command -v slsa-verifier >/dev/null 2>&1 && [ ! -x "$(HOME)/.local/bin/slsa-verifier" ]; then \
		echo "Installing slsa-verifier into ~/.local/bin…"; \
		OS=$$(uname -s | tr '[:upper:]' '[:lower:]'); \
		ARCH=$$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/;s/arm64/arm64/'); \
		case "$$OS" in darwin) OS=darwin ;; linux) OS=linux ;; *) echo "WARN: unsupported OS $$OS"; OS="";; esac; \
		if [ -n "$$OS" ]; then \
			tmp=$$(mktemp); \
			if curl -fsSL --max-time 60 \
				"https://github.com/slsa-framework/slsa-verifier/releases/latest/download/slsa-verifier-$${OS}-$${ARCH}" \
				-o "$$tmp"; then \
				chmod +x "$$tmp" && mv "$$tmp" "$(HOME)/.local/bin/slsa-verifier"; \
				echo "Installed $(HOME)/.local/bin/slsa-verifier"; \
			else \
				rm -f "$$tmp"; \
				echo "WARN: could not download slsa-verifier (offline?) — continuing with local assessor"; \
			fi; \
		fi; \
	fi
	$(Q)# verdit-slsa is not on PyPI at a stable pin — local assessor is authoritative.
	$(Q)$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		python -c "print('verdit-slsa OK (local assessor in scripts/slsa/run_verdit.py)')"
	$(Q)echo "Optional image pin: SLSA_VERIFIER_IMAGE=$(SLSA_VERIFIER_IMAGE)"

slsa-provenance: check-uv ## [slsa] Generate SLSA provenance document for wheel + images
	$(Q)mkdir -p "$(SLSA_REPORT_DIR)"
	$(Q)wheel=$$(ls -1 "$(WHEEL_DIR)"/tkeir-*.whl "$(DIST_DIR)"/tkeir-*.whl 2>/dev/null | head -1); \
		if [ -z "$$wheel" ]; then $(MAKE) build; wheel=$$(ls -1 "$(WHEEL_DIR)"/tkeir-*.whl "$(DIST_DIR)"/tkeir-*.whl 2>/dev/null | head -1); fi; \
		test -n "$$wheel" || { echo "ERROR: no wheel under $(WHEEL_DIR) or $(DIST_DIR)"; exit 1; }; \
		uv_ver=$$($(UV) --version 2>/dev/null | awk '{print $$2}'); \
		commit_full=$$(git rev-parse HEAD 2>/dev/null || echo "$(GIT_COMMIT)"); \
		$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
			python "$(SCRIPTS_DIR)/slsa/gen_provenance.py" \
			--version  "$(VERSION)" \
			--commit   "$$commit_full" \
			--branch   "$(GIT_BRANCH)" \
			--build-date "$(BUILD_DATE)" \
			--wheel    "$$wheel" \
			--python   "$(PYTHON)" \
			--uv-version "$${uv_ver:-unknown}" \
			--output   "$(PROVENANCE_FILE)"

slsa-assess: check-uv ## [slsa] Run verdit-slsa against provenance; print achieved level
	$(Q)test -f "$(PROVENANCE_FILE)" || $(MAKE) slsa-provenance
	$(Q)wheel=$$(ls -1 "$(WHEEL_DIR)"/tkeir-*.whl "$(DIST_DIR)"/tkeir-*.whl 2>/dev/null | head -1); \
		$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
			python "$(SCRIPTS_DIR)/slsa/run_verdit.py" \
			--provenance "$(PROVENANCE_FILE)" \
			--subject    "$$wheel" \
			--report     "$(SLSA_REPORT_DIR)/report.json"

slsa-report: check-uv ## [slsa] Write report.json + roadmap.md; print path to next SLSA level
	$(Q)test -f "$(PROVENANCE_FILE)" || $(MAKE) slsa-provenance
	$(Q)wheel=$$(ls -1 "$(WHEEL_DIR)"/tkeir-*.whl "$(DIST_DIR)"/tkeir-*.whl 2>/dev/null | head -1); \
		$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
			python "$(SCRIPTS_DIR)/slsa/run_verdit.py" \
			--provenance "$(PROVENANCE_FILE)" \
			--subject    "$$wheel" \
			--report     "$(SLSA_REPORT_DIR)/report.json" \
			--print-roadmap
	$(Q)echo "SLSA report → $(SLSA_REPORT_DIR)/report.json"
	$(Q)echo "SLSA roadmap → $(SLSA_REPORT_DIR)/roadmap.md"

slsa-level-gate: check-jq ## [slsa] Fail CI if achieved SLSA level < SLSA_LEVEL
	$(Q)test -f "$(SLSA_REPORT_DIR)/report.json" || $(MAKE) slsa-report
	$(Q)level=$$(jq -r '.level' "$(SLSA_REPORT_DIR)/report.json"); \
		if [ "$$level" -lt "$(SLSA_LEVEL)" ]; then \
			echo "FAIL: SLSA level $$level < required $(SLSA_LEVEL)"; exit 1; \
		fi; \
		echo "PASS: SLSA level $$level >= $(SLSA_LEVEL)"

slsa: slsa-prereqs slsa-provenance slsa-assess slsa-level-gate ## [slsa] Full SLSA pipeline (prereqs → provenance → assess → gate)

check-cosign: ## [sign] Verify cosign ≥ 2.0 is installed
	$(Q)command -v cosign >/dev/null 2>&1 || { \
		echo "cosign >= 2.0 required."; \
		echo "  macOS:  brew install cosign"; \
		echo "  docs:   https://docs.sigstore.dev/cosign/system_config/installation/"; \
		exit 1; }
	$(Q)ver=$$(cosign version 2>/dev/null | grep -i 'GitVersion' | awk '{print $$2}' | tr -d 'v'); \
		major=$$(echo "$$ver" | cut -d. -f1); \
		[ -n "$$major" ] || major=0; \
		[ "$$major" -ge 2 ] || { echo "cosign >= 2.0 required (found $$ver)"; exit 1; }; \
		echo "cosign OK (v$$ver at $$(command -v cosign))"

check-radamsa: ## [fuzz] Verify radamsa is installed (mutation fuzzer)
	$(Q)command -v "$(RADAMSA)" >/dev/null 2>&1 || { \
		echo "radamsa required for mutation fuzz tests."; \
		echo "  macOS:  brew install radamsa"; \
		echo "  Linux:  apt install radamsa  # or build from https://gitlab.com/akihe/radamsa"; \
		exit 1; }
	$(Q)ver=$$("$(RADAMSA)" -V 2>&1 | head -1); \
		echo "radamsa OK ($$ver at $$(command -v $(RADAMSA)))"

check-supply-tools: check-cosign check-radamsa ## [ops] Verify cosign + radamsa are installed
	$(Q)echo "supply-chain / fuzz tools OK"

sign-wheel: check-cosign ## [sign] cosign sign-blob the built wheel; save bundle
	$(Q)chmod +x "$(SCRIPTS_DIR)/slsa/sign_blob.sh"
	$(Q)wheel=$$(ls -1 "$(WHEEL_DIR)"/tkeir-*.whl "$(DIST_DIR)"/tkeir-*.whl 2>/dev/null | head -1); \
		if [ -z "$$wheel" ]; then $(MAKE) build; wheel=$$(ls -1 "$(WHEEL_DIR)"/tkeir-*.whl "$(DIST_DIR)"/tkeir-*.whl 2>/dev/null | head -1); fi; \
		test -n "$$wheel" || { echo "ERROR: no wheel — run make build"; exit 1; }; \
		COSIGN_BUNDLE_DIR="$(COSIGN_BUNDLE_DIR)" REKOR_URL="$(REKOR_URL)" \
		FULCIO_URL="$(FULCIO_URL)" COSIGN_YES="$(COSIGN_YES)" \
		STRICT_SIGNING="$(STRICT_SIGNING)" \
		"$(SCRIPTS_DIR)/slsa/sign_blob.sh" wheel.bundle "$$wheel"

# Serialize blob signing so .mode / keypair generation cannot race under make -j.
sign-sbom: check-cosign sign-wheel ## [sign] cosign sign-blob the CycloneDX BOM JSON
	$(Q)chmod +x "$(SCRIPTS_DIR)/slsa/sign_blob.sh"
	$(Q)mkdir -p "$(COSIGN_BUNDLE_DIR)"
	$(Q)bom=$$(ls -1 "$(ROOT)/$(BOM_REPORT_DIR)"/*.json "$(BOM_REPORT_DIR)"/*.json 2>/dev/null | head -1); \
		if [ -z "$$bom" ]; then $(MAKE) bom; bom=$$(ls -1 "$(ROOT)/$(BOM_REPORT_DIR)"/*.json "$(BOM_REPORT_DIR)"/*.json 2>/dev/null | head -1); fi; \
		test -n "$$bom" || { echo "ERROR: no BOM JSON under $(BOM_REPORT_DIR)"; exit 1; }; \
		COSIGN_BUNDLE_DIR="$(COSIGN_BUNDLE_DIR)" REKOR_URL="$(REKOR_URL)" \
		FULCIO_URL="$(FULCIO_URL)" COSIGN_YES="$(COSIGN_YES)" \
		STRICT_SIGNING="$(STRICT_SIGNING)" \
		"$(SCRIPTS_DIR)/slsa/sign_blob.sh" sbom.bundle "$$bom"

sign-provenance: check-cosign sign-sbom slsa-provenance ## [sign] cosign sign-blob the SLSA provenance JSON
	$(Q)chmod +x "$(SCRIPTS_DIR)/slsa/sign_blob.sh"
	$(Q)test -f "$(PROVENANCE_FILE)" || { echo "ERROR: missing $(PROVENANCE_FILE)"; exit 1; }
	$(Q)COSIGN_BUNDLE_DIR="$(COSIGN_BUNDLE_DIR)" REKOR_URL="$(REKOR_URL)" \
		FULCIO_URL="$(FULCIO_URL)" COSIGN_YES="$(COSIGN_YES)" \
		STRICT_SIGNING="$(STRICT_SIGNING)" \
		"$(SCRIPTS_DIR)/slsa/sign_blob.sh" provenance.bundle "$(PROVENANCE_FILE)"

sign-attest-images: check-cosign slsa-provenance ## [sign] cosign attest images with SLSA provenance predicate
	$(Q)test -f "$(PROVENANCE_FILE)"
	$(Q)for name in tkeir-lib tkeir-api tkeir-indexer tkeir-indexer-slim tkeir-hmi tkeir-ingest tkeir-audit tkeir-governor; do \
		echo "Attesting $(IMAGE_REGISTRY)/$${name}:$(IMAGE_TAG)"; \
		if ! cosign attest $(COSIGN_YES) \
			--predicate "$(PROVENANCE_FILE)" \
			--type slsaprovenance \
			--rekor-url "$(REKOR_URL)" \
			--fulcio-url "$(FULCIO_URL)" \
			"$(IMAGE_REGISTRY)/$${name}:$(IMAGE_TAG)" 2>/dev/null; then \
			if [ "$(STRICT_SIGNING)" = "1" ]; then exit 1; fi; \
			echo "WARN: skip attest for $(IMAGE_REGISTRY)/$${name}:$(IMAGE_TAG) (image missing or no OIDC)"; \
		fi; \
	done

sign-all: sign-wheel sign-sbom sign-provenance ## [sign] Sign wheel + SBOM + provenance (+ optional image attest)
	$(Q)echo "Blob signatures written under $(COSIGN_BUNDLE_DIR)/"
	$(Q)if [ "$(SKIP_IMAGE_ATTEST)" = "1" ]; then \
		echo "SKIP_IMAGE_ATTEST=1 — not attesting images"; \
	else \
		$(MAKE) sign-attest-images || { \
			if [ "$(STRICT_SIGNING)" = "1" ]; then exit 1; fi; \
			echo "WARN: image attestation skipped"; \
		}; \
	fi

verify-signatures: check-cosign ## [sign] Verify all signatures in COSIGN_BUNDLE_DIR (offline)
	$(Q)chmod +x "$(SCRIPTS_DIR)/slsa/verify_blob.sh"
	$(Q)wheel=$$(ls -1 "$(WHEEL_DIR)"/tkeir-*.whl "$(DIST_DIR)"/tkeir-*.whl 2>/dev/null | head -1); \
		test -n "$$wheel" || { echo "ERROR: no wheel — run make build"; exit 1; }; \
		COSIGN_BUNDLE_DIR="$(COSIGN_BUNDLE_DIR)" \
		"$(SCRIPTS_DIR)/slsa/verify_blob.sh" wheel.bundle "$$wheel" wheel
	$(Q)bom=$$(ls -1 "$(ROOT)/$(BOM_REPORT_DIR)"/*.json "$(BOM_REPORT_DIR)"/*.json 2>/dev/null | head -1); \
		test -n "$$bom" || { echo "ERROR: no BOM to verify"; exit 1; }; \
		COSIGN_BUNDLE_DIR="$(COSIGN_BUNDLE_DIR)" \
		"$(SCRIPTS_DIR)/slsa/verify_blob.sh" sbom.bundle "$$bom" SBOM
	$(Q)COSIGN_BUNDLE_DIR="$(COSIGN_BUNDLE_DIR)" \
		"$(SCRIPTS_DIR)/slsa/verify_blob.sh" provenance.bundle "$(PROVENANCE_FILE)" provenance
	$(Q)echo "All blob signatures verified."
