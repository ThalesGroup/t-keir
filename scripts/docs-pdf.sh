#!/bin/bash
# Generate T-KEIR documentation as a single PDF (MkDocs nav order).
# Pipeline only: Markdown → HTML → PDF via PyMuPDF (no Vespa / site server).
set -euo pipefail

script_path="$(cd "$(dirname "$0")" && pwd)"
root_path="$(cd "$script_path/.." && pwd)"

python_version="${PYTHON_VERSION:-3.11}"
output_path="${DOCS_PDF_OUTPUT:-$root_path/output/docs/tkeir-docs.pdf}"
mkdocs_yml="${MKDOCS_YML:-$root_path/mkdocs.yml}"
docs_dir="${DOCS_DIR:-$root_path/docs}"
keep_html="${DOCS_PDF_KEEP_HTML:-}"

usage() {
    echo "usage: $(basename "$0") [-h] [-o FILE]"
    echo ""
    echo "Generate PDF documentation from docs (MkDocs navigation order)."
    echo ""
    echo "Options:"
    echo "  -o FILE               Output PDF (default: output/docs/tkeir-docs.pdf)"
    echo "  -h, --help            Show this help"
    echo ""
    echo "Environment:"
    echo "  DOCS_PDF_OUTPUT       Same as -o"
    echo "  DOCS_PDF_KEEP_HTML    If set, also write intermediate HTML to this path"
    echo "  DOCS_PDF_SKIP_MERMAID If 1/true, keep Mermaid as source (no mmdc/npx)"
    echo "  MKDOCS_YML / DOCS_DIR Override MkDocs config / docs directory"
    echo "  PYTHON_VERSION        Python for uv (default: 3.11)"
    echo ""
    echo "Notes:"
    echo "  Expands pymdownx --8<-- snippets (compliance catalogues, configs)."
    echo "  Mermaid fences render via mmdc or: npx @mermaid-js/mermaid-cli"
    echo "  Requires: markdown (uv --with), pymupdf, and Node npx for diagrams."
    echo ""
    echo "Make:"
    echo "  make docs-pdf"
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage ;;
        -o)
            output_path="$2"
            shift 2
            ;;
        -o=*)
            output_path="${1#-o=}"
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            ;;
    esac
done

if [ ! -f "$mkdocs_yml" ]; then
    echo "MkDocs config not found: $mkdocs_yml" >&2
    exit 1
fi

if [ ! -d "$docs_dir" ]; then
    echo "Docs directory not found: $docs_dir" >&2
    exit 1
fi

mkdir -p "$(dirname "$output_path")"

extra_args=()
if [ -n "$keep_html" ]; then
    extra_args+=(--keep-html "$keep_html")
fi

echo "T-KEIR docs → PDF"
echo "  mkdocs : $mkdocs_yml"
echo "  docs   : $docs_dir"
echo "  output : $output_path"
echo ""

cd "$root_path"
DOCS_PDF_OUTPUT="$output_path" \
DOCS_DIR="$docs_dir" \
MKDOCS_YML="$mkdocs_yml" \
    uv run --project "$root_path/tkeir" --python "$python_version" --with markdown \
    python "$script_path/docs_pdf.py" \
    -o "$output_path" \
    --docs-dir "$docs_dir" \
    --mkdocs-yml "$mkdocs_yml" \
    "${extra_args[@]+"${extra_args[@]}"}"
