#!/bin/bash
set -euo pipefail

VESPA_URL="${VESPA_URL:-http://localhost:8080}"

echo "[+] Vespa smoke test against ${VESPA_URL}"

curl -fsS "${VESPA_URL}/search/" \
  -H "Content-Type: application/json" \
  -d '{"yql":"select source_doc_id, title from tkeir_document where true limit 3","hits":3}' \
  | jq .

curl -fsS "${VESPA_URL}/search/" \
  -H "Content-Type: application/json" \
  -d '{"yql":"select chunk_id, text_raw from chunk where true limit 3","hits":3}' \
  | jq .

echo "[✓] document + chunk schemas are queryable"
