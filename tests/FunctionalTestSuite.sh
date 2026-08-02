#!/bin/bash
set -e
script_path=$(cd "$(dirname "$0")" && pwd)
cd "$script_path"

ACTIVE_FUNCTIONAL_TESTS=(
    functional_tests/TestPipeline.py
    functional_tests/TestOkfWorkflow.py
    functional_tests/TestWorkspaceApi.py
    functional_tests/TestJsonRecordsApi.py
    functional_tests/TestAgentServiceApi.py
    functional_tests/TestGovernorHttp.py
    functional_tests/TestHealthContracts.py
)

uv run --project ../tkeir --python 3.11 pytest "${ACTIVE_FUNCTIONAL_TESTS[@]}" -q "$@"
