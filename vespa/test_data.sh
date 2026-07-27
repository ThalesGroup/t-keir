#!/bin/bash
set -euo pipefail

VESPA_URL="${VESPA_URL:-http://localhost:8080}"
USER_SPACE="${VESPA_USER_SPACE:-dev@tkeir}"

echo "[+] Vespa smoke test against ${VESPA_URL}"

curl -fsS "${VESPA_URL}/search/" \
  -H "Content-Type: application/json" \
  -d '{"yql":"select source_ref, chunk_text from global where true limit 3","hits":3,"ranking.profile":"unranked"}' \
  | jq .

curl -fsS "${VESPA_URL}/search/" \
  -H "Content-Type: application/json" \
  -d "{\"yql\":\"select source_ref, chunk_text from user where true limit 3\",\"hits\":3,\"ranking.profile\":\"unranked\",\"streaming.groupname\":\"${USER_SPACE}\"}" \
  | jq .

echo "[✓] global + user schemas are queryable"
