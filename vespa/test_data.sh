#!/bin/bash
set -euo pipefail

VESPA_URL="${VESPA_URL:-http://localhost:8080}"
USER_SPACE="${VESPA_USER_SPACE:-dev@tkeir}"

echo "[+] Vespa smoke test against ${VESPA_URL}"

echo "[i] global passages (chunk_text):"
curl -fsS "${VESPA_URL}/search/" \
    -H "Content-Type: application/json" \
    -d '{"yql":"select source_ref, chunk_text from global where true limit 3","hits":3,"ranking.profile":"unranked"}' \
    | jq '{total: .root.fields.totalCount, hits: [.root.children[]?.fields.source_ref]}'

echo "[i] ontology_concept catalog:"
curl -fsS "${VESPA_URL}/search/" \
    -H "Content-Type: application/json" \
    -d '{"yql":"select concept_id, preferred_label from ontology_concept where true limit 3","hits":3,"ranking.profile":"unranked"}' \
    | jq '{total: .root.fields.totalCount, hits: [.root.children[]?.fields.concept_id]}'

echo "[i] ontology_triple catalog:"
curl -fsS "${VESPA_URL}/search/" \
    -H "Content-Type: application/json" \
    -d '{"yql":"select triple_key from ontology_triple where true limit 3","hits":3,"ranking.profile":"unranked"}' \
    | jq '{total: .root.fields.totalCount, hits: [.root.children[]?.fields.triple_key]}'

echo "[i] corpus_doc documents:"
curl -fsS "${VESPA_URL}/search/" \
    -H "Content-Type: application/json" \
    -d '{"yql":"select source_ref, title from corpus_doc where true limit 3","hits":3,"ranking.profile":"unranked"}' \
    | jq '{total: .root.fields.totalCount, hits: [.root.children[]?.fields.source_ref]}'

echo "[i] user passages:"
curl -fsS "${VESPA_URL}/search/" \
    -H "Content-Type: application/json" \
    -d "{\"yql\":\"select source_ref, chunk_text from user where true limit 3\",\"hits\":3,\"ranking.profile\":\"unranked\",\"streaming.groupname\":\"${USER_SPACE}\"}" \
    | jq '{total: .root.fields.totalCount, hits: [.root.children[]?.fields.source_ref]}'

echo "[✓] global + ontology_concept + ontology_triple + corpus_doc + user schemas are queryable"
