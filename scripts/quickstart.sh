#!/bin/bash
# Run the T-KEIR pipeline on bundled test fixtures.
set -euo pipefail

script_path="$(cd "$(dirname "$0")" && pwd)"
root_path="$(cd "$script_path/.." && pwd)"
tkeir_path="$root_path/tkeir"
fixtures_path="$tkeir_path/tests/fixtures"

config_path="${QUICKSTART_CONFIG:-$tkeir_path/configs/pipeline.json}"
output_path="${QUICKSTART_OUTPUT:-$root_path/output/quickstart}"
transformers_cache="${TRANSFORMERS_CACHE:-$root_path/.cache/models}"
python_version="${PYTHON_VERSION:-3.11}"

usage() {
    echo "usage: $(basename "$0") [options]"
    echo "  QUICKSTART_CONFIG      pipeline config (default: tkeir/configs/pipeline.json)"
    echo "  QUICKSTART_OUTPUT      output directory (default: output/quickstart)"
    echo "  TRANSFORMERS_CACHE     model cache path (default: .cache/models)"
    exit 1
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    usage
fi

if [ ! -f "$config_path" ]; then
    echo "Pipeline config not found: $config_path" >&2
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

datatype_for_converter_fixture() {
    case "${1##*.}" in
        pdf) echo "pdf" ;;
        docx) echo "docx" ;;
        rtf) echo "rtf" ;;
        odt)
            echo "Skip unsupported converter fixture (MarkItDown has no ODT converter): $1" >&2
            return 1
            ;;
        *) return 1 ;;
    esac
}

pipeline_failures=0

echo "T-KEIR quickstart"
echo "  config : $config_path"
echo "  output : $output_path"
echo ""

if [ -d "$fixtures_path/test-raw/raw" ]; then
    run_pipeline "$fixtures_path/test-raw/raw" raw "$output_path/test-raw/raw" || true
fi

if [ -d "$fixtures_path/test-raw/mail" ]; then
    run_pipeline "$fixtures_path/test-raw/mail" email "$output_path/test-raw/mail" || true
fi

if [ -d "$fixtures_path/test-raw/raw-target" ]; then
    run_pipeline "$fixtures_path/test-raw/raw-target" raw "$output_path/test-raw/raw-target" || true
fi

converter_output="$output_path/converter-tests"
mkdir -p "$converter_output"
found_converter_fixtures=0
for fixture in "$fixtures_path"/converter_test*.*; do
    [ -f "$fixture" ] || continue
    found_converter_fixtures=1
    datatype="$(datatype_for_converter_fixture "$fixture")" || {
        echo "Skip unsupported converter fixture: $fixture" >&2
        continue
    }
    run_pipeline "$fixture" "$datatype" "$converter_output" || true
done

if [ "$found_converter_fixtures" -eq 0 ]; then
    echo "No converter_test* fixtures found in $fixtures_path" >&2
    exit 1
fi

if [ "$pipeline_failures" -gt 0 ]; then
    echo ""
    echo "Quickstart finished with $pipeline_failures failure(s). See messages above." >&2
    exit 1
fi

echo ""
echo "Quickstart complete. Results in: $output_path"
