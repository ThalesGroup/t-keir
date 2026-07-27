#!/usr/bin/env bash
# Install spaCy language models (wheel download with spacy download fallback).
# Skips download when all required models are already importable.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TKEIR_DIR="${ROOT}/tkeir"
UV="${UV:-uv}"
PYTHON="${PYTHON:-3.11}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-3}"
FORCE_SPACY_MODELS="${FORCE_SPACY_MODELS:-0}"

if ! command -v "${UV}" >/dev/null 2>&1; then
    echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

SPACY_MODELS=(
    en_core_web_sm
    en_core_web_md
    fr_core_news_sm
    fr_core_news_md
    xx_ent_wiki_sm
)

models_already_present() {
    cd "${TKEIR_DIR}"
    "${UV}" run --no-sync --python "${PYTHON}" python - <<'PY'
import importlib.util
import sys

models = [
    "en_core_web_sm",
    "en_core_web_md",
    "fr_core_news_sm",
    "fr_core_news_md",
    "xx_ent_wiki_sm",
]
missing = [m for m in models if importlib.util.find_spec(m) is None]
if missing:
    print("missing:" + ",".join(missing), flush=True)
    sys.exit(1)
print("present:" + ",".join(models), flush=True)
sys.exit(0)
PY
}

if [ "${FORCE_SPACY_MODELS}" != "1" ] && models_already_present; then
    echo "WARN: spaCy language models already installed — skipping download."
    echo "      Set FORCE_SPACY_MODELS=1 to reinstall."
    exit 0
fi

install_with_uv() {
    local attempt=1
    while [ "${attempt}" -le "${MAX_ATTEMPTS}" ]; do
        if "${UV}" sync --directory "${TKEIR_DIR}" --group models; then
            return 0
        fi
        echo "spaCy model sync failed (attempt ${attempt}/${MAX_ATTEMPTS})" >&2
        attempt=$((attempt + 1))
        sleep 5
    done
    return 1
}

install_with_spacy_download() {
    echo "Falling back to python -m spacy download ..." >&2
    cd "${TKEIR_DIR}"
    "${UV}" run --no-sync --python "${PYTHON}" python - <<'PY'
import subprocess
import sys

models = [
    "en_core_web_sm",
    "en_core_web_md",
    "fr_core_news_sm",
    "fr_core_news_md",
    "xx_ent_wiki_sm",
]
for model in models:
    print("Installing", model, flush=True)
    subprocess.run(
        [sys.executable, "-m", "spacy", "download", model],
        check=True,
    )
PY
}

if install_with_uv; then
    echo "spaCy models installed via uv sync --group models"
    exit 0
fi

install_with_spacy_download
echo "spaCy models installed via spacy download"
