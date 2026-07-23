#!/usr/bin/env bash
# Generate Annex IV style technical documentation pack (AI Act evidence hook).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${ANNEX_IV_DIR:-$ROOT/reports/compliance/annex-iv}"
mkdir -p "$OUT"

export ROOT OUT VERSION
DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat > "$OUT/README.md" <<EOF
# Annex IV technical documentation pack

Generated: ${DATE}
Version: ${VERSION}

> Engineering evidence only — **not legal advice**.

## Contents

| File | Source |
|------|--------|
| \`architecture.md\` | ADR-0001 summary pointer |
| \`evaluation_report.md\` | Copy of BEIR report when present |
| \`model-cards.md\` | Models from \`deploy/versions.lock.yaml\` |
| \`risk-log.md\` | Known gaps (full-mesh SPIFFE, etc.) |

EOF

cat > "$OUT/architecture.md" <<'EOF'
# System architecture

See `docs/adr/0001-platform-architecture.md` and deployment profiles
(`docs/deployment/index.md`).

Primary data path: ingest → NLP pipeline → Vespa two-level index → RAG API → HMI.
Control plane: Keycloak (IAM), governor (runtime), audit (ActionRecords + WORM).
EOF

if [ -f "$ROOT/docs/evaluation_report.md" ]; then
  cp "$ROOT/docs/evaluation_report.md" "$OUT/evaluation_report.md"
else
  printf '%s\n' "# Evaluation report" "" "Run \`make beir-eval\` to generate." "" > "$OUT/evaluation_report.md"
fi

python3 - <<'PY'
from pathlib import Path
import os
import yaml

root = Path(os.environ["ROOT"])
out = Path(os.environ["OUT"])
lock = yaml.safe_load((root / "deploy/versions.lock.yaml").read_text(encoding="utf-8")) or {}
models = lock.get("models") or {}
lines = ["# Model cards (from versions.lock.yaml)\n"]
for key, meta in models.items():
    lines.append(f"## {key}\n")
    for k, v in (meta or {}).items():
        lines.append(f"- **{k}**: `{v}`\n")
    lines.append("\n")
(out / "model-cards.md").write_text("".join(lines), encoding="utf-8")
PY

cat > "$OUT/risk-log.md" <<'EOF'
# Risk / known gaps log

| Item | Status | Mitigation |
|------|--------|------------|
| SPIRE / SPIFFE (agents) | Adopted (ADR-0008) | Compose `spire` + `SPIFFE_*` on tkeir-agent |
| Full-mesh SPIFFE (all services) | Later | Agents first; JWT + correlation for RAG/ingest |
| Full Kubeflow | Scaffold only | Platform profile flag; pipelines skeleton |
| Audit p95 e2e SLO | Not yet CI-gated | Unit tests + compose-smoke; e2e workflow planned |
| External LLM / OCR llm mode | Data egress | Documented in GDPR mapping |
EOF

echo "✅ Annex IV pack → $OUT"
