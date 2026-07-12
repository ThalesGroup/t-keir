#!/bin/bash
set -e
script_path=$(dirname "$0")
cd "$script_path"

ACTIVE_FUNCTIONAL_TESTS=(
    functional_tests/TestPipeline.py
)

uv run --python 3.11 pytest "${ACTIVE_FUNCTIONAL_TESTS[@]}" -q "$@"
