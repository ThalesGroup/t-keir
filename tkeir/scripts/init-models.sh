#!/usr/bin/env bash
######################################################
# Author : Eric Blaudez
# Copyright (c) 2022 by THALES
# All right reserved.
# Description : Build tokenizer MWE resource (tkeir_mwe.pkl)
#
# Usage:
#   ./scripts/init-models.sh [MODEL_CACHE_PATH]
#
# MODEL_CACHE_PATH sets TRANSFORMERS_CACHE (default: unset /
# inherited). Prefer ``make init-models`` from the repo root.
#######################################################
set -euo pipefail

script_path="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# tkeir/scripts → tkeir package root
tkeir_root="$(cd "${script_path}/.." && pwd)"

usage() {
    echo "Usage: init-models.sh [MODEL_CACHE_PATH]" >&2
    echo "  Builds resources/modeling/tokenizer/en/tkeir_mwe.pkl" >&2
    exit 1
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    usage
fi

if [ "$#" -gt 1 ]; then
    usage
fi

if [ "$#" -eq 1 ]; then
    export TRANSFORMERS_CACHE="$1"
    export MODEL_PATH="$1"
fi

resources_en="${tkeir_root}/resources/modeling/tokenizer/en"
out="${resources_en}/tkeir_mwe.pkl"

if [ -f "${out}" ]; then
    echo "WARN: annotation model already exists — skipping: ${out}"
    echo "      Delete it and re-run to regenerate."
    exit 0
fi

cd "${tkeir_root}"
uv run --python 3.11 tkeir-create-annotation-resource \
    --entries-file "${resources_en}/annotation-resources.json" \
    --output "${out}"
