#!/usr/bin/env bash
# Build unified CycloneDX BOM (SBOM + AIBOM) for T-Keir.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TKEIR_DIR="${TKEIR_DIR:-$ROOT/tkeir}"
CONFIG="${BOM_CONFIG:-$ROOT/scripts/bom/config.yaml}"
if [[ "$CONFIG" != /* ]]; then
  CONFIG="$ROOT/$CONFIG"
fi
BOM_DIR="${BOM_REPORT_DIR:-$ROOT/reports/bom}"
if [[ "$BOM_DIR" != /* ]]; then
  BOM_DIR="$ROOT/$BOM_DIR"
fi
SPEC_VERSION="${BOM_SPEC_VERSION:-1.6}"
PYTHON="${BOM_PYTHON:-$TKEIR_DIR/.venv/bin/python}"

if [ ! -x "$PYTHON" ]; then
  echo "error: virtualenv python not found at ${PYTHON} — run 'make ci-deps' first" >&2
  exit 1
fi

echo "▶ Generating unified BOM (CycloneDX ${SPEC_VERSION}: SBOM + AIBOM)..."
cd "$TKEIR_DIR"
uv run --python 3.11 python "$ROOT/scripts/bom/generate_bom.py" \
  --config "$CONFIG" \
  --output-dir "$BOM_DIR" \
  --spec-version "$SPEC_VERSION" \
  --python "$PYTHON" \
  --tkeir-dir "$TKEIR_DIR"

echo "▶ Validating unified BOM artifacts..."
for artifact in \
  "$BOM_DIR/tkeir.cdx.json" \
  "$BOM_DIR/views/dependencies-runtime.cdx.json" \
  "$BOM_DIR/views/dependencies-ci.cdx.json" \
  "$BOM_DIR/views/dependencies-environment.cdx.json"
do
  if [ ! -s "$artifact" ]; then
    echo "error: missing or empty BOM artifact: ${artifact}" >&2
    exit 1
  fi
  uv run --python 3.11 python -c "import json; bom=json.load(open('${artifact}')); assert bom.get('bomFormat')=='CycloneDX', bom"
done

if [ ! -s "$BOM_DIR/tkeir.cdx.xml" ]; then
  echo "error: missing or empty BOM artifact: ${BOM_DIR}/tkeir.cdx.xml" >&2
  exit 1
fi

echo "✅ Unified BOM construction passed (reports in ${BOM_DIR})"
