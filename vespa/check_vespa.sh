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
# GET on the type root is 400 without a visit/selection; that is expected.
curl -sS -o /dev/null -w "document_api_global=%{http_code}\n" \
  "${DOC_ENDPOINT}/document/v1/default/global/docid/" || true
curl -sS -o /dev/null -w "document_api_user=%{http_code}\n" \
  "${DOC_ENDPOINT}/document/v1/default/user/group/${USER_SPACE}/" || true
curl -sS -o /dev/null -w "document_api_ontology_concept=%{http_code}\n" \
  "${DOC_ENDPOINT}/document/v1/default/ontology_concept/docid/" || true

print_header "Schema search smoke (no feed)"
curl -fsS -X POST "${DOC_ENDPOINT}/search/" \
  -H "Content-Type: application/json" \
  -d '{
    "yql": "select source_ref, chunk_text from global where true",
    "hits": 1,
    "ranking.profile": "unranked"
  }' | jq '{schema:"global", total:.root.fields.totalCount}'

curl -fsS -X POST "${DOC_ENDPOINT}/search/" \
  -H "Content-Type: application/json" \
  -d '{
    "yql": "select concept_id from ontology_concept where true",
    "hits": 1,
    "ranking.profile": "unranked"
  }' | jq '{schema:"ontology_concept", total:.root.fields.totalCount}'

user_ok=0
for _ in 1 2 3 4 5; do
  if curl -fsS -X POST "${DOC_ENDPOINT}/search/" \
    -H "Content-Type: application/json" \
    -d "{
      \"yql\": \"select source_ref, chunk_text from user where true\",
      \"hits\": 1,
      \"ranking.profile\": \"unranked\",
      \"streaming.groupname\": \"${USER_SPACE}\"
    }" | jq '{schema:"user", total:.root.fields.totalCount}'; then
    user_ok=1
    break
  fi
  sleep 2
done
if [[ "${user_ok}" -ne 1 ]]; then
  echo "[!] user schema search not ready yet (streaming cluster still starting)"
fi

if [[ "${VESPA_HEALTHCHECK_FEED:-0}" != "1" ]]; then
  echo -e "\n[✓] Vespa search APIs are up (no documents fed)."
  echo "    Optional write probe: VESPA_HEALTHCHECK_FEED=1 make vespa-check"
  exit 0
fi

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
