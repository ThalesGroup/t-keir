#!/usr/bin/env bash
# Export a running Keycloak realm back to deploy/keycloak/realm-tkeir.json.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${OUT:-$ROOT/deploy/keycloak/realm-tkeir.json}"
KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8082}"
ADMIN="${KEYCLOAK_ADMIN:-admin}"
PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
REALM="${KEYCLOAK_REALM:-tkeir}"

TOKEN="$(curl -fsS -X POST \
  "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
  -d "client_id=admin-cli" \
  -d "username=${ADMIN}" \
  -d "password=${PASSWORD}" \
  -d "grant_type=password" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"

curl -fsS \
  -H "Authorization: Bearer ${TOKEN}" \
  "${KEYCLOAK_URL}/admin/realms/${REALM}" \
  -o "${OUT}.partial"

# Prefer partial-export endpoint when available
if curl -fsS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${KEYCLOAK_URL}/admin/realms/${REALM}/partial-export?exportClients=true&exportGroupsAndRoles=true" \
  -o "${OUT}.new"; then
  mv "${OUT}.new" "${OUT}"
  rm -f "${OUT}.partial"
else
  mv "${OUT}.partial" "${OUT}"
fi

echo "Exported realm ${REALM} → ${OUT}"
