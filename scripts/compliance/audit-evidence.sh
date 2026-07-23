#!/usr/bin/env bash
# Build compliance evidence pack under reports/evidence/<version>/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="${VERSION:-$(cd "$ROOT" && git describe --tags --always --dirty 2>/dev/null || echo 0.0.0-dev)}"
OUT="${EVIDENCE_DIR:-$ROOT/reports/evidence/$VERSION}"
mkdir -p "$OUT"
export OUT VERSION

echo "▶ Evidence pack → $OUT"

# Copy existing scan artifacts when present
for src in \
  "$ROOT/reports/bom" \
  "$ROOT/reports/security" \
  "$ROOT/coverage-reports" \
  "$ROOT/reports/dependency-check"
do
  if [ -d "$src" ]; then
    name="$(basename "$src")"
    mkdir -p "$OUT/$name"
    cp -R "$src"/. "$OUT/$name/" 2>/dev/null || true
  fi
done

# Capture versions.lock + ADRs list
cp "$ROOT/deploy/versions.lock.yaml" "$OUT/versions.lock.yaml" 2>/dev/null || true
find "$ROOT/docs/adr" -name '*.md' -print > "$OUT/adr-index.txt" 2>/dev/null || true

# Sample policy bundle SHA (if Rego present)
if [ -f "$ROOT/deploy/policies/app/tkeir-intents.rego" ]; then
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$ROOT/deploy/policies/app/tkeir-intents.rego" > "$OUT/policy-bundle.sha256"
  else
    sha256sum "$ROOT/deploy/policies/app/tkeir-intents.rego" > "$OUT/policy-bundle.sha256"
  fi
fi

# Manifest
python3 - <<PY
import json, os, pathlib, datetime
out = pathlib.Path(os.environ["OUT"])
manifest = {
  "schema": "tkeir.evidence.v1",
  "version": os.environ["VERSION"],
  "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
  "disclaimer": "Engineering evidence, not legal advice.",
  "artifacts": sorted(p.name for p in out.iterdir() if p.name != "manifest.json"),
}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps(manifest, indent=2))
PY

echo "✅ Evidence pack ready: $OUT"
