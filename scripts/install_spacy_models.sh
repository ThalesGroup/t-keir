#!/usr/bin/env bash
# Extract spaCy 3.6 wheels into tkeir/resources/modeling/spacy (setup/install).
# Core models (en/fr/xx) are required. Extra European sm models are optional.
# Arabic uses spaCy blank:ar (no Explosion 3.6 wheel).
# FORCE_SPACY_MODELS=1 re-downloads even when models are already present.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TKEIR_DIR="${ROOT}/tkeir"
UV="${UV:-uv}"
PYTHON="${PYTHON:-3.11}"

if ! command -v "${UV}" >/dev/null 2>&1; then
    echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

cd "${TKEIR_DIR}"
exec "${UV}" run --no-sync --python "${PYTHON}" python -m thot.tools.install_spacy_models "$@"
