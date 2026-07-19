#!/bin/bash

set -euo pipefail

print_header() {
  echo -e "\n=== $1 ==="
}

VESPA_HOST="${VESPA_HOST:-localhost}"
DOC_ENDPOINT="http://${VESPA_HOST}:8080"
CONFIG_ENDPOINT="http://${VESPA_HOST}:19071"
USER_SPACE="${VESPA_USER_SPACE:-dev@tkeir}"

print_header "Checking Vespa config server"
curl -fsS "${CONFIG_ENDPOINT}/state/v1/health" | jq .

print_header "Checking deployed application"
STATUS=$(curl -fsS "${CONFIG_ENDPOINT}/application/v2/tenant/default/application/default")
echo "$STATUS" | jq .

print_header "Checking document APIs"
curl -fsS "${DOC_ENDPOINT}/document/v1/" | jq .

print_header "Inserting test parent document (streaming group=${USER_SPACE})"
DOC_KEY="healthcheck-doc"
curl -fsS -X POST \
  "${DOC_ENDPOINT}/document/v1/default/tkeir_document/group/${USER_SPACE}/${DOC_KEY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"fields\": {
      \"user_space\": \"${USER_SPACE}\",
      \"source_doc_id\": \"healthcheck://document\",
      \"title\": \"Vespa health check\",
      \"content\": [\"Parent document content\"],
      \"json_ld\": \"\",
      \"shacl_status\": \"PASSED\"
    }
  }" | jq .

print_header "Inserting test chunk"
curl -fsS -X POST \
  "${DOC_ENDPOINT}/document/v1/default/chunk/group/${USER_SPACE}/healthcheck-chunk" \
  -H "Content-Type: application/json" \
  -d "{
    \"fields\": {
      \"user_space\": \"${USER_SPACE}\",
      \"chunk_id\": \"healthcheck-chunk\",
      \"doc_ref\": \"id:default:tkeir_document:g=${USER_SPACE}:${DOC_KEY}\",
      \"parent_title\": \"Vespa health check\",
      \"parent_content\": [\"Parent document content\"],
      \"text_raw\": \"Chunk health check text\",
      \"chunk_embedding\": $(python3 - <<'PY'
import json
print(json.dumps([0.0] * 384))
PY
),
      \"questions_embeddings\": {}
    }
  }" | jq .

print_header "Streaming search smoke (group=${USER_SPACE})"
curl -fsS -X POST "${DOC_ENDPOINT}/search/" \
  -H "Content-Type: application/json" \
  -d "{
    \"yql\": \"select * from chunk where true\",
    \"hits\": 1,
    \"streaming.groupname\": \"${USER_SPACE}\"
  }" | jq .

print_header "Cleaning up test documents"
curl -fsS -X DELETE \
  "${DOC_ENDPOINT}/document/v1/default/chunk/group/${USER_SPACE}/healthcheck-chunk" | jq .
curl -fsS -X DELETE \
  "${DOC_ENDPOINT}/document/v1/default/tkeir_document/group/${USER_SPACE}/${DOC_KEY}" | jq .

echo -e "\n[✓] Vespa streaming document + chunk APIs are operational."
