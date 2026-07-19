#!/usr/bin/env bash
# EU compliance audit orchestrator (OPA + T-KEIR evidence).
# Exits 0 with a warning when `opa` is not on PATH (CI-friendly).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OPA_DIR="$ROOT/compliance/opa"
POLICIES="$OPA_DIR/policies"
INPUT_DIR="$OPA_DIR/input"
OVERRIDES="$OPA_DIR/overrides.yaml"

cd "$ROOT"

if ! command -v opa >/dev/null 2>&1; then
  echo "[eu-audit] WARNING: opa not found on PATH — skipping EU compliance audit."
  echo "[eu-audit] Install: https://www.openpolicyagent.org/docs/latest/#running-opa"
  exit 0
fi

VERSION="$(git describe --tags --always --dirty 2>/dev/null || echo unknown)"
STAMP="$(date +%Y%m%d_%H%M%S)"
INPUT_JSON="${COMPLIANCE_INPUT_JSON:-$INPUT_DIR/generated_${STAMP}.json}"
OUT_DIR="${COMPLIANCE_OUT_DIR:-$ROOT/reports/compliance/eu-audit/$VERSION}"

mkdir -p "$INPUT_DIR" "$OUT_DIR"

echo "[eu-audit] generating input → $INPUT_JSON"
python3 "$OPA_DIR/collectors/input_generator.py" \
  --repo "$ROOT" \
  --overrides "$OVERRIDES" \
  --output "$INPUT_JSON"

echo "[eu-audit] checking policies"
# Policies use classic (v0) Rego per compliance/opa/policies/lib/common.rego;
# --v0-compatible keeps them loadable under OPA 1.x, which defaults to v1 syntax.
opa check --v0-compatible "$POLICIES"

eval_pkg() {
  local pkg="$1"
  local out="$2"
  opa eval \
    --v0-compatible \
    --format json \
    --data "$POLICIES" \
    --input "$INPUT_JSON" \
    --package "$pkg" \
    "data.${pkg}.summary" \
    > "$out"
}

echo "[eu-audit] evaluating regulations"
eval_pkg "eu.ai_act" "$OUT_DIR/opa-ai_act.json"
eval_pkg "eu.cra"    "$OUT_DIR/opa-cra.json"
eval_pkg "eu.gdpr"   "$OUT_DIR/opa-gdpr.json"
eval_pkg "eu.nis2"   "$OUT_DIR/opa-nis2.json"
eval_pkg "eu.dora"   "$OUT_DIR/opa-dora.json"
eval_pkg "eu.pld"    "$OUT_DIR/opa-pld.json"

cp "$INPUT_JSON" "$OUT_DIR/input.json"

echo "[eu-audit] Generating OSCAL Assessment Results + POA&M"
SSP_UUID="tkeir-ssp-$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
python3 "$OPA_DIR/oscal/opa_to_oscal.py" \
  --results-dir "$OUT_DIR" \
  --output-dir "$OUT_DIR/oscal" \
  --ssp-uuid "$SSP_UUID" \
  --version "$VERSION"

echo "[eu-audit] building report"
set +e
python3 "$OPA_DIR/report_generator.py" \
  --input "$INPUT_JSON" \
  --outdir "$OUT_DIR" \
  --version "$VERSION" \
  --oscal-dir "$OUT_DIR/oscal" \
  --ai-act "$OUT_DIR/opa-ai_act.json" \
  --cra "$OUT_DIR/opa-cra.json" \
  --gdpr "$OUT_DIR/opa-gdpr.json" \
  --nis2 "$OUT_DIR/opa-nis2.json" \
  --dora "$OUT_DIR/opa-dora.json" \
  --pld "$OUT_DIR/opa-pld.json"
rc=$?
set -e

echo "[eu-audit] OSCAL AR  → $OUT_DIR/oscal/assessment_results.json"
echo "[eu-audit] OSCAL PAM → $OUT_DIR/oscal/poam.json"
echo "[eu-audit] publishing full results into MkDocs"
python3 "$OPA_DIR/scripts/gen_doc_results.py" --report "$OUT_DIR/report.json"
echo "[eu-audit] artefacts under $OUT_DIR"
# Non-zero from report_generator means gaps found — still exit 0 for make ci
# unless COMPLIANCE_STRICT=1
if [ "${COMPLIANCE_STRICT:-0}" = "1" ] && [ "$rc" -ne 0 ]; then
  exit "$rc"
fi
exit 0
