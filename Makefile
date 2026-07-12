# T-KEIR — local development Makefile
.PHONY: help setup install check-uv check-docker install-tesseract install-spacy-models build wheel init-models \
	test test-unit test-functional test-coverage coverage \
	lint format typecheck liccheck complexity pip-audit \
	bom sbom aibom trivy owasp-dependency-check \
	docs docs-build pipeline quickstart install-workspace ci-deps ci clean devcontainer

UV ?= uv
PYTHON ?= 3.11
COMPOSE ?= docker compose
TRIVY_IMAGE ?= aquasec/trivy:0.58.2
OWASP_DC_IMAGE ?= owasp/dependency-check:12.1.0
OWASP_DC_FAIL_CVSS ?= 7
TRIVY_SEVERITY ?= HIGH,CRITICAL
BOM_SPEC_VERSION ?= 1.6
BOM_REPORT_DIR ?= reports/bom
BOM_CONFIG ?= scripts/bom/config.yaml
BOM_PYTHON ?= tkeir/.venv/bin/python
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
TKEIR_DIR := $(ROOT)/tkeir
TESTS_DIR := $(TKEIR_DIR)/tests
CONFIGS_DIR := $(TKEIR_DIR)/configs
SCRIPTS_DIR := $(ROOT)/scripts
COVERAGE_REPORT_DIR := $(ROOT)/coverage-reports
SECURITY_REPORT_DIR ?= $(ROOT)/reports/security

PIPELINE_CONFIG ?= $(CONFIGS_DIR)/pipeline.json
PIPELINE_INPUT ?= $(TKEIR_DIR)/tests/fixtures/test-raw/raw
PIPELINE_OUTPUT ?= /tmp/tkeir-pipeline-out
PIPELINE_TYPE ?= auto
TRANSFORMERS_CACHE ?= $(ROOT)/.cache/models
WORKSPACE ?= $(ROOT)/workspace
DOCS_PORT ?= 8000

# Python trees checked by lint, format, mypy, and complexity tools.
PYTHON_SOURCES := thot tests

# Xenon thresholds for the full tree (radon reports; xenon gates CI).
XENON_MAX_ABSOLUTE ?= F
XENON_MAX_MODULES ?= F
XENON_MAX_AVERAGE ?= A

-include .env
export

help:
	@echo "T-KEIR — common targets"
	@echo "  make setup              Install deps, Tesseract OCR, and tokenizer resources"
	@echo "  make install            Sync Python environment (uv) in tkeir/"
	@echo "  make install-spacy-models  Install spaCy language models (optional group)"
	@echo "  make build              Build wheel (output: dist/)"
	@echo "  make init-models        Build tkeir_mwe.pkl from annotation resources"
	@echo "  make test               Unit + functional tests"
	@echo "  make test-unit          Run unit test suite"
	@echo "  make test-functional    Run functional test suite"
	@echo "  make coverage           Run coverage suite (fail-under 90%)"
	@echo "  make lint               black + isort checks on thot/ and tests/"
	@echo "  make format             Apply black + isort"
	@echo "  make typecheck          mypy on thot/ and tests/"
	@echo "  make liccheck           Verify dependency licenses"
	@echo "  make complexity         radon + xenon on thot/ and tests/"
	@echo "  make pip-audit          Scan Python dependencies for known CVEs"
	@echo "  make bom                Unified CycloneDX SBOM + AIBOM"
	@echo "  make aibom              Alias for make bom"
	@echo "  make trivy              Filesystem + config scan (Docker)"
	@echo "  make owasp-dependency-check  OWASP Dependency-Check (Docker)"
	@echo "  Reopen in Dev Container     .devcontainer/ (uv, Tesseract, Docker socket)"
	@echo "  make devcontainer           Shell into devcontainer (bash .devcontainer/enter-devcontainer.sh)"
	@echo "  make docs               MkDocs dev server at http://127.0.0.1:$(DOCS_PORT)"
	@echo "  make docs-build         Static HTML documentation under tkeir/site/"
	@echo "  make pipeline           Run tkeir-pipeline on PIPELINE_INPUT (PIPELINE_TYPE=auto)"
	@echo "  make quickstart         Run pipeline on test-raw and converter_test fixtures"
	@echo "  make install-workspace  Full wheel install via install.sh into WORKSPACE"
	@echo "  make ci                 Lint, types, tests, coverage, licenses, complexity, security, BOM"
	@echo "  make clean              Remove build artifacts and caches"
	@echo ""
	@echo "Variables: PIPELINE_INPUT PIPELINE_OUTPUT PIPELINE_TYPE TRANSFORMERS_CACHE WORKSPACE"

check-uv:
	@command -v $(UV) >/dev/null 2>&1 || { \
		echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/"; \
		exit 1; \
	}

check-docker:
	@command -v docker >/dev/null 2>&1 || { \
		echo "Docker is required. Install: https://docs.docker.com/get-docker/"; \
		exit 1; \
	}
	@$(COMPOSE) version >/dev/null 2>&1 || { \
		echo "Docker Compose v2 required (docker compose)"; \
		exit 1; \
	}

install: check-uv
	$(UV) sync --directory $(TKEIR_DIR) --group dev

ci-deps: check-uv
	$(UV) sync --directory $(TKEIR_DIR) --group dev --group models

install-spacy-models: check-uv
	@chmod +x "$(SCRIPTS_DIR)/install_spacy_models.sh"
	@bash "$(SCRIPTS_DIR)/install_spacy_models.sh"

build wheel: check-uv
	$(UV) build --directory $(TKEIR_DIR)
	@echo "Built wheel in $(ROOT)/dist/"

init-models: install
	@mkdir -p "$(TRANSFORMERS_CACHE)"
	cd $(TKEIR_DIR) && TRANSFORMERS_CACHE="$(TRANSFORMERS_CACHE)" \
        $(UV) run --no-sync --python $(PYTHON) \
		tkeir-create-annotation-resource \
		--entries-file resources/modeling/tokenizer/en/annotation-resources.json \
		--output resources/modeling/tokenizer/en/tkeir_mwe.pkl

install-tesseract:
	@chmod +x "$(SCRIPTS_DIR)/install_tesseract.sh"
	@bash "$(SCRIPTS_DIR)/install_tesseract.sh"

setup: install install-spacy-models install-tesseract init-models
	@echo ""
	@echo "Setup complete."
	@echo "  Run pipeline: make pipeline"
	@echo "  Or demo:      make quickstart"

test-unit: ci-deps
	cd $(TESTS_DIR) && bash UnitTestSuite.sh

test-functional: ci-deps
	cd $(TESTS_DIR) && bash FunctionalTestSuite.sh

test: test-unit test-functional

test-coverage coverage: ci-deps
	cd $(TESTS_DIR) && bash CoverageFast.sh

lint: ci-deps
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with black --with isort \
		black --check $(PYTHON_SOURCES)
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with isort \
		isort --check-only $(PYTHON_SOURCES)

format: ci-deps
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with black --with isort \
		black $(PYTHON_SOURCES)
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with isort \
		isort $(PYTHON_SOURCES)

typecheck: ci-deps
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		--with mypy \
		mypy $(PYTHON_SOURCES)

liccheck: ci-deps
	cd $(TKEIR_DIR) && $(UV) export --frozen --no-dev --no-emit-project \
		-o .requirements-liccheck.txt
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		liccheck -s MIT -r .requirements-liccheck.txt
	rm -f $(TKEIR_DIR)/.requirements-liccheck.txt

complexity: ci-deps
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		radon cc $(PYTHON_SOURCES) -a -nb
	$(UV) run --directory $(TKEIR_DIR) --python $(PYTHON) \
		xenon --max-absolute $(XENON_MAX_ABSOLUTE) \
			--max-modules $(XENON_MAX_MODULES) \
			--max-average $(XENON_MAX_AVERAGE) \
			$(PYTHON_SOURCES)

PIP_AUDIT_IGNORE ?= \
	--ignore-vuln CVE-2026-49851 \
	--ignore-vuln CVE-2026-44708 \
	--ignore-vuln CVE-2026-44897 \
	--ignore-vuln PYSEC-2026-168 \
	--ignore-vuln PYSEC-2026-141 \
	--ignore-vuln PYSEC-2026-1999 \
	--ignore-vuln PYSEC-2026-1998 \
	--ignore-vuln PYSEC-2026-1994 \
	--ignore-vuln PYSEC-2026-1996

pip-audit: ci-deps
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		pip-audit --skip-editable $(PIP_AUDIT_IGNORE)

bom: ci-deps
	@chmod +x "$(SCRIPTS_DIR)/build_bom.sh"
	BOM_SPEC_VERSION=$(BOM_SPEC_VERSION) BOM_REPORT_DIR=$(BOM_REPORT_DIR) \
		BOM_CONFIG=$(BOM_CONFIG) BOM_PYTHON=$(ROOT)/$(BOM_PYTHON) \
		TKEIR_DIR=$(TKEIR_DIR) \
		"$(SCRIPTS_DIR)/build_bom.sh"

sbom: bom
	@echo "note: make sbom is an alias for make bom (unified SBOM + AIBOM)"

aibom: bom
	@echo "note: make aibom is an alias for make bom (unified SBOM + AIBOM)"

trivy: check-docker ci-deps
	@chmod +x "$(SCRIPTS_DIR)/run_trivy.sh"
	TRIVY_IMAGE=$(TRIVY_IMAGE) TRIVY_SEVERITY=$(TRIVY_SEVERITY) \
		SECURITY_REPORT_DIR=$(SECURITY_REPORT_DIR) TKEIR_DIR=$(TKEIR_DIR) \
		"$(SCRIPTS_DIR)/run_trivy.sh"

owasp-dependency-check: check-docker ci-deps
	@chmod +x "$(SCRIPTS_DIR)/run_owasp_dependency_check.sh"
	OWASP_DC_IMAGE=$(OWASP_DC_IMAGE) OWASP_DC_FAIL_CVSS=$(OWASP_DC_FAIL_CVSS) \
		TKEIR_DIR=$(TKEIR_DIR) \
		"$(SCRIPTS_DIR)/run_owasp_dependency_check.sh"

docs: ci-deps
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		--with mkdocs --with mkdocs-material --with mkdocs-render-swagger \
		mkdocs serve -a 127.0.0.1:$(DOCS_PORT)

docs-build: ci-deps
	cd $(TKEIR_DIR) && $(UV) run --python $(PYTHON) \
		--with mkdocs --with mkdocs-material --with mkdocs-render-swagger \
		mkdocs build
	@echo "Built static site: $(TKEIR_DIR)/site/index.html"

pipeline: ci-deps install-spacy-models
	@mkdir -p "$(PIPELINE_OUTPUT)"
	cd $(TKEIR_DIR) && TRANSFORMERS_CACHE="$(TRANSFORMERS_CACHE)" \
		$(UV) run --no-sync --python $(PYTHON) tkeir-pipeline \
		-c "$(PIPELINE_CONFIG)" \
		-i "$(PIPELINE_INPUT)" \
		-o "$(PIPELINE_OUTPUT)" \
		-t "$(PIPELINE_TYPE)"
	@echo "Pipeline output: $(PIPELINE_OUTPUT)"

QUICKSTART_CONFIG ?= $(PIPELINE_CONFIG)
QUICKSTART_OUTPUT ?= $(ROOT)/output/quickstart

quickstart: ci-deps init-models
	QUICKSTART_CONFIG="$(QUICKSTART_CONFIG)" \
		QUICKSTART_OUTPUT="$(QUICKSTART_OUTPUT)" \
		TRANSFORMERS_CACHE="$(TRANSFORMERS_CACHE)" \
		bash "$(SCRIPTS_DIR)/quickstart.sh"

install-workspace: check-uv
	@test -n "$(WORKSPACE)" || { echo "WORKSPACE is required"; exit 1; }
	bash "$(ROOT)/install.sh" "$(WORKSPACE)"

devcontainer: check-docker
	bash "$(ROOT)/.devcontainer/enter-devcontainer.sh"

ci: ci-deps lint typecheck test coverage liccheck complexity pip-audit bom trivy owasp-dependency-check
	@echo "All quality gates passed."

clean:
	rm -rf dist build .pytest_cache .mypy_cache .ruff_cache htmlcov .cache reports
	rm -rf "$(COVERAGE_REPORT_DIR)"
	rm -f $(TESTS_DIR)/.coverage $(TESTS_DIR)/.coverage_* $(TESTS_DIR)/testsuite.log
	rm -rf $(TKEIR_DIR)/site
	find $(TKEIR_DIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
