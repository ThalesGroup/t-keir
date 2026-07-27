#!/bin/bash

set -euo pipefail

print_header() {
  echo -e "\n=== $1 ==="
}

VESPA_HOST="${VESPA_HOST:-localhost}"
DOC_ENDPOINT="http://${VESPA_HOST}:8080"
CONFIG_ENDPOINT="http://${VESPA_HOST}:19071"
USER_SPACE="${VESPA_USER_SPACE:-dev@tkeir}"
DENSE_DIM="${VESPA_DENSE_DIM:-1024}"

print_header "Checking Vespa config server"
curl -fsS "${CONFIG_ENDPOINT}/state/v1/health" | jq .

print_header "Checking deployed application"
STATUS=$(curl -fsS "${CONFIG_ENDPOINT}/application/v2/tenant/default/application/default")
echo "$STATUS" | jq .

print_header "Checking document APIs"
curl -fsS -o /dev/null -w "document_api_global=%{http_code}\n" \
  "${DOC_ENDPOINT}/document/v1/default/global/docid/" || true
curl -fsS -o /dev/null -w "document_api_user=%{http_code}\n" \
  "${DOC_ENDPOINT}/document/v1/default/user/group/${USER_SPACE}/" || true

DENSE_VEC=$(python3 - <<PY
import json
print(json.dumps([0.0] * int("${DENSE_DIM}")))
PY
)

print_header "Inserting test global passage"
curl -fsS -X POST \
  "${DOC_ENDPOINT}/document/v1/default/global/docid/healthcheck-global" \
  -H "Content-Type: application/json" \
  -d "{
    \"fields\": {
      \"source_ref\": \"healthcheck://global\",
      \"chunk_text\": \"Global catalog health check text\",
      \"dense_vector\": {\"values\": ${DENSE_VEC}},
      \"sparse_vector\": {},
      \"ontology_concepts\": [\"healthcheck\"]
    }
  }" | jq .

print_header "Inserting test user passage (streaming group=${USER_SPACE})"
curl -fsS -X POST \
  "${DOC_ENDPOINT}/document/v1/default/user/group/${USER_SPACE}/healthcheck-user" \
  -H "Content-Type: application/json" \
  -d "{
    \"fields\": {
      \"userspace_id\": \"${USER_SPACE}\",
      \"source_ref\": \"healthcheck://user\",
      \"chunk_text\": \"User space health check text\",
      \"dense_vector\": {\"values\": ${DENSE_VEC}},
      \"sparse_vector\": {},
      \"ontology_concepts\": [\"healthcheck\"]
    }
  }" | jq .

print_header "Global search smoke"
curl -fsS -X POST "${DOC_ENDPOINT}/search/" \
  -H "Content-Type: application/json" \
  -d "{
    \"yql\": \"select source_ref, chunk_text from global where true\",
    \"hits\": 1,
    \"ranking.profile\": \"unranked\"
  }" | jq .

print_header "User streaming search smoke (group=${USER_SPACE})"
curl -fsS -X POST "${DOC_ENDPOINT}/search/" \
  -H "Content-Type: application/json" \
  -d "{
    \"yql\": \"select source_ref, chunk_text from user where true\",
    \"hits\": 1,
    \"ranking.profile\": \"unranked\",
    \"streaming.groupname\": \"${USER_SPACE}\"
  }" | jq .

print_header "Cleaning up test documents"
curl -fsS -X DELETE \
  "${DOC_ENDPOINT}/document/v1/default/global/docid/healthcheck-global" | jq .
curl -fsS -X DELETE \
  "${DOC_ENDPOINT}/document/v1/default/user/group/${USER_SPACE}/healthcheck-user" | jq .

echo -e "\n[✓] Vespa global + user APIs are operational."
