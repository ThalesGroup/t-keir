#!/bin/bash
# Run the T-KEIR pipeline (analysis only — no Vespa indexing) on test-raw fixtures.
set -euo pipefail

script_path="$(cd "$(dirname "$0")" && pwd)"
root_path="$(cd "$script_path/.." && pwd)"
tkeir_path="$root_path/tkeir"
fixtures_path="$tkeir_path/tests/fixtures/test-raw"

config_path="${QUICKSTART_CONFIG:-$tkeir_path/configs/pipeline.yaml}"
output_path="${QUICKSTART_OUTPUT:-$root_path/output/quickstart}"
transformers_cache="${TRANSFORMERS_CACHE:-$root_path/.cache/models}"
python_version="${PYTHON_VERSION:-3.11}"

usage() {
    echo "usage: $(basename "$0") [options]"
    echo "  QUICKSTART_CONFIG      pipeline config (default: tkeir/configs/pipeline.yaml)"
    echo "  QUICKSTART_OUTPUT      output directory (default: output/quickstart)"
    echo "  TRANSFORMERS_CACHE     model cache path (default: .cache/models)"
    echo ""
    echo "Runs tkeir-pipeline only on tkeir/tests/fixtures/test-raw (no indexing)."
    exit 1
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    usage
fi

if [ ! -f "$config_path" ]; then
    echo "Pipeline config not found: $config_path" >&2
    exit 1
fi

if [ ! -d "$fixtures_path" ]; then
    echo "Fixtures not found: $fixtures_path" >&2
    exit 1
fi

if [ ! -f "$tkeir_path/resources/modeling/tokenizer/en/tkeir_mwe.pkl" ]; then
    echo "Tokenizer resources missing. Run: make setup" >&2
    exit 1
fi

run_pipeline() {
    local input_path="$1"
    local datatype="$2"
    local output_dir="$3"

    echo "* pipeline -t $datatype -i $input_path -> $output_dir"
    mkdir -p "$output_dir"
    if (
        cd "$tkeir_path"
        TRANSFORMERS_CACHE="$transformers_cache" \
            uv run --no-sync --python "$python_version" tkeir-pipeline \
            -c "$config_path" \
            -i "$input_path" \
            -o "$output_dir" \
            -t "$datatype"
    ); then
        return 0
    fi
    echo "FAILED: $input_path" >&2
    pipeline_failures=$((pipeline_failures + 1))
    return 1
}

pipeline_failures=0
found_inputs=0

echo "T-KEIR quickstart (pipeline only)"
echo "  fixtures: $fixtures_path"
echo "  config  : $config_path"
echo "  output  : $output_path"
echo ""

if [ -d "$fixtures_path/raw" ]; then
    found_inputs=1
    run_pipeline "$fixtures_path/raw" raw "$output_path/raw" || true
fi

if [ -d "$fixtures_path/mail" ]; then
    found_inputs=1
    run_pipeline "$fixtures_path/mail" email "$output_path/mail" || true
fi

if [ -d "$fixtures_path/raw-target" ]; then
    found_inputs=1
    run_pipeline "$fixtures_path/raw-target" raw "$output_path/raw-target" || true
fi

if [ "$found_inputs" -eq 0 ]; then
    echo "No test-raw inputs found under $fixtures_path" >&2
    exit 1
fi

if [ "$pipeline_failures" -gt 0 ]; then
    echo ""
    echo "Quickstart finished with $pipeline_failures failure(s). See messages above." >&2
    exit 1
fi

echo ""
echo "Quickstart complete (pipeline only — no indexing). Results in: $output_path"
