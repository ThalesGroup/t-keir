#!/usr/bin/env bash
# Install spaCy language models (direct wheel install; no project rebuild).
# Skips download when all required models are already importable.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TKEIR_DIR="${ROOT}/tkeir"
UV="${UV:-uv}"
PYTHON="${PYTHON:-3.11}"
FORCE_SPACY_MODELS="${FORCE_SPACY_MODELS:-0}"

if ! command -v "${UV}" >/dev/null 2>&1; then
    echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

# Keep versions aligned with tkeir/pyproject.toml [dependency-groups].models
SPACY_MODEL_WHEELS=(
    "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.6.0/en_core_web_sm-3.6.0-py3-none-any.whl"
    "https://github.com/explosion/spacy-models/releases/download/en_core_web_md-3.6.0/en_core_web_md-3.6.0-py3-none-any.whl"
    "https://github.com/explosion/spacy-models/releases/download/fr_core_news_sm-3.6.0/fr_core_news_sm-3.6.0-py3-none-any.whl"
    "https://github.com/explosion/spacy-models/releases/download/fr_core_news_md-3.6.0/fr_core_news_md-3.6.0-py3-none-any.whl"
    "https://github.com/explosion/spacy-models/releases/download/xx_ent_wiki_sm-3.6.0/xx_ent_wiki_sm-3.6.0-py3-none-any.whl"
)

models_already_present() {
    cd "${TKEIR_DIR}"
    # --no-sync: never rebuild the editable tkeir package just to probe imports
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

echo "Installing spaCy model wheels into ${TKEIR_DIR}/.venv (uv pip)…"
# Install wheels only — do not `uv sync` the project (that rebuilds editable
# tkeir and can hang while hatchling walks multi-GB resources/modeling).
cd "${TKEIR_DIR}"
"${UV}" pip install --python "${PYTHON}" "${SPACY_MODEL_WHEELS[@]}"

if models_already_present; then
    echo "spaCy models installed via uv pip"
    exit 0
fi

echo "Falling back to python -m spacy download ..." >&2
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
echo "spaCy models installed via spacy download"
