#!/usr/bin/env bash
# Runs inside the devcontainer after first create (postCreateCommand).
set -euo pipefail

cd /workspace

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv not found in PATH — rebuild the devcontainer image" >&2
  exit 1
fi

if ! command -v tesseract >/dev/null 2>&1; then
  echo "warning: tesseract not found — PDF OCR may fail" >&2
fi

bash .devcontainer/ensure-venv.sh

# Pin Python 3.11 (spaCy/thinc have no wheels for 3.12+).
uv python install 3.11 >/dev/null 2>&1 || true

make install
echo ""
echo "Devcontainer ready — you are in /workspace"
echo "  How to enter next time: Cursor/VS Code → Command Palette → Dev Containers: Reopen in Container"
echo "  Docs: docs/devcontainer.md  |  .devcontainer/README.md"
echo ""
echo "  make setup       — spaCy models, Tesseract, optional MWE pickle"
echo "  make ci          — lint, tests, coverage, security scans"
echo "  make quickstart  — pipeline demo on fixtures"
echo "  make bootstrap && make index && make rag  — Vespa RAG stack"
echo "  cd tkeir-hmi && npm install && npm run dev           — Web UI on :3000"
echo "  (host Ollama required: ollama serve && ollama pull bge-m3; OLLAMA_BASE_URL uses host.docker.internal)"
