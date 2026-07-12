.PHONY: sync start init bootstrap check test test-py clean clean-db logs index index-fixtures rag rag-query

UV ?= uv
VESPA_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
REPO_ROOT := $(abspath $(VESPA_DIR)/..)
TKEIR_DIR := $(REPO_ROOT)/tkeir
INDEX_INPUT ?= $(TKEIR_DIR)/tests/indexing/output
INDEX_FIXTURES_INPUT := $(TKEIR_DIR)/tests/indexing/input
RAG_URL ?= http://localhost:8090
RAG_QUERY ?= Who is Rob Brown?
RAG_LANGUAGE ?= en
RAG_HITS ?= 20

# Sync T-KEIR Python dependencies (tools live under thot/tools/)
sync:
	cd $(TKEIR_DIR) && $(UV) sync --group dev --python 3.11

# Start Vespa container
start:
	./start_vespa.sh

# Deploy schemas to Vespa (container must already be running)
init: sync
	cd $(TKEIR_DIR) && $(UV) run python -m thot.tools.search.init_vespa --skip-start

# Full bootstrap (start + deploy)
bootstrap: sync
	cd $(TKEIR_DIR) && $(UV) run python -m thot.tools.search.init_vespa

# Health check
check:
	./check_vespa.sh

# Vespa query smoke test
test:
	./test_data.sh

# Python unit tests for search tools
test-py: sync
	cd $(TKEIR_DIR) && $(UV) run pytest tests/unittests/TestVespaClient.py tests/unittests/TestOntologyUtils.py -q

# Build portable pipeline JSON fixtures for Vespa indexing
index-fixtures:
	cd $(REPO_ROOT) && $(MAKE) pipeline \
		PIPELINE_INPUT=$(INDEX_FIXTURES_INPUT) \
		PIPELINE_OUTPUT=$(INDEX_INPUT) \
		PIPELINE_TYPE=auto
	@test -n "$$(find "$(INDEX_INPUT)" -maxdepth 1 -name '*.pipeline.json' -print -quit)" || { \
		echo "No *.pipeline.json files produced in $(INDEX_INPUT)"; \
		echo "Ensure spaCy models are installed: make install-spacy-models"; \
		exit 1; \
	}

# Index pipeline JSON outputs from tkeir/tests/indexing/output
index: sync init
	@test -d "$(INDEX_INPUT)" || { \
		echo "Missing indexing fixtures: $(INDEX_INPUT)"; \
		echo "Run: cd vespa && make index-fixtures"; \
		exit 1; \
	}
	@test -n "$$(find "$(INDEX_INPUT)" -maxdepth 1 -name '*.pipeline.json' -print -quit)" || { \
		echo "No *.pipeline.json files in $(INDEX_INPUT)"; \
		echo "Run: cd vespa && make index-fixtures"; \
		exit 1; \
	}
	@echo "Indexing from $(INDEX_INPUT)"
	cd $(TKEIR_DIR) && $(UV) run python -m thot.tools.search.index_documents -i "$(INDEX_INPUT)"

# Run FastAPI RAG service (spaCy models required for morphosyntax query refinement)
rag: sync
	cd $(REPO_ROOT) && $(MAKE) install-spacy-models
	cd $(TKEIR_DIR) && $(UV) run python -m thot.tools.search.app

# Send a sample RAG query (override: make rag-query RAG_QUERY="your question")
rag-query:
	curl -fsS "$(RAG_URL)/rag/query" \
		-H "Content-Type: application/json" \
		-d "$$(jq -nc --arg query "$(RAG_QUERY)" --arg language "$(RAG_LANGUAGE)" --argjson hits $(RAG_HITS) '{query:$$query,language:$$language,hits:$$hits}')" \
		| jq .

# Wipe Vespa indexed data (container + docker volume)
clean-db:
	./clean_db.sh

# Stop container only
clean:
	docker stop vespa || true
	docker rm vespa || true

# Tail Vespa logs
logs:
	docker logs -f vespa
