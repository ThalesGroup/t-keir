#!/usr/bin/env bash
# Smoke-test a running Compose stack (core + optional profiles).
set -euo pipefail

API_URL="${API_URL:-http://localhost:8090}"
HMI_URL="${HMI_URL:-http://localhost:3000}"
GOVERNOR_URL="${GOVERNOR_URL:-http://localhost:8094}"
AUDIT_URL="${AUDIT_URL:-http://localhost:8093}"
INGEST_URL="${INGEST_URL:-http://localhost:8091}"
KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8082}"

CHECK_GOVERNOR="${CHECK_GOVERNOR:-auto}"
CHECK_AUDIT="${CHECK_AUDIT:-auto}"
CHECK_INGEST="${CHECK_INGEST:-auto}"
CHECK_AUTH="${CHECK_AUTH:-auto}"

failures=0

check_health() {
  local name="$1"
  local url="$2"
  printf '  %-18s %s ... ' "$name" "$url"
  if status="$(curl -fsS --max-time 15 "${url%/}/health" 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status",""))' 2>/dev/null)" \
    && { [ "$status" = "ok" ] || [ "$status" = "ready" ] || [ "$status" = "healthy" ]; }; then
    echo "PASS ($status)"
    return 0
  fi
  echo "FAIL"
  failures=$((failures + 1))
  return 1
}

check_hmi() {
  printf '  %-18s %s ... ' "tkeir-hmi" "${HMI_URL}/api/healthz"
  if curl -fsS --max-time 15 "${HMI_URL%/}/api/healthz" >/dev/null 2>&1; then
    echo "PASS"
    return 0
  fi
  echo "FAIL"
  failures=$((failures + 1))
  return 1
}

reachable() {
  curl -fsS --max-time 3 "$1" >/dev/null 2>&1
}

should_check() {
  local mode="$1"
  local url="$2"
  case "$mode" in
    1|true|yes|on) return 0 ;;
    0|false|no|off) return 1 ;;
    auto) reachable "${url%/}/health" ;;
    *) return 1 ;;
  esac
}

echo "=== Compose smoke test ==="

check_health "tkeir-api" "$API_URL"
check_hmi

if should_check "$CHECK_GOVERNOR" "$GOVERNOR_URL"; then
  check_health "tkeir-governor" "$GOVERNOR_URL"
fi

if should_check "$CHECK_AUDIT" "$AUDIT_URL"; then
  check_health "tkeir-audit" "$AUDIT_URL"
fi

if should_check "$CHECK_INGEST" "$INGEST_URL"; then
  check_health "tkeir-ingest" "$INGEST_URL"
fi

if should_check "$CHECK_AUTH" "$KEYCLOAK_URL"; then
  printf '  %-18s %s ... ' "keycloak" "${KEYCLOAK_URL}/realms/tkeir"
  if curl -fsS --max-time 15 "${KEYCLOAK_URL%/}/realms/tkeir" >/dev/null 2>&1; then
    echo "PASS"
  else
    echo "FAIL"
    failures=$((failures + 1))
  fi
fi

# Minimal RAG query + correlation id check (optional — Vespa + models must be warm)
if [ "${COMPOSE_SMOKE_RAG:-0}" = "1" ]; then
  printf '  %-18s %s ... ' "rag/query" "$API_URL"
  tmp="$(mktemp)"
  if curl -fsS --max-time 120 -D "${tmp}.hdr" -o "$tmp" -X POST "${API_URL%/}/rag/query" \
    -H 'content-type: application/json' \
    -d '{"query":"smoke test","language":"en","hits":1}'; then
    cid="$(awk -F': ' 'tolower($1)=="x-correlation-id"{gsub("\r","",$2); print $2; exit}' "${tmp}.hdr" || true)"
    if [ -n "$cid" ]; then
      echo "PASS (X-Correlation-Id=$cid)"
      if should_check "$CHECK_AUDIT" "$AUDIT_URL"; then
        printf '  %-18s %s ... ' "audit/report" "$cid"
        if curl -fsS --max-time 15 \
          "${AUDIT_URL%/}/audit/report?correlation_id=${cid}" >/dev/null 2>&1; then
          echo "PASS"
        else
          echo "FAIL (record not yet in audit store — enable AUDIT_SINK_MODE=dual)"
          failures=$((failures + 1))
        fi
      fi
    else
      echo "PASS (no X-Correlation-Id header)"
    fi
  else
    echo "FAIL (set COMPOSE_SMOKE_RAG=0 to skip)"
    failures=$((failures + 1))
  fi
  rm -f "$tmp" "${tmp}.hdr"
fi

if [ "${CHECK_OBS:-auto}" != "0" ] && [ "${CHECK_OBS:-auto}" != "off" ]; then
  if curl -fsS --max-time 3 "http://localhost:3001/api/health" >/dev/null 2>&1 \
    || [ "${CHECK_OBS:-auto}" = "1" ]; then
    printf '  %-18s %s ... ' "grafana" "http://localhost:3001/api/health"
    if curl -fsS --max-time 10 "http://localhost:3001/api/health" >/dev/null 2>&1; then
      echo "PASS"
    else
      echo "FAIL"
      failures=$((failures + 1))
    fi
  fi
fi

if [ "${CHECK_MINIO:-auto}" != "0" ] && [ "${CHECK_MINIO:-auto}" != "off" ]; then
  if curl -fsS --max-time 3 "http://localhost:9000/minio/health/live" >/dev/null 2>&1 \
    || [ "${CHECK_MINIO:-auto}" = "1" ]; then
    printf '  %-18s %s ... ' "minio" "http://localhost:9000/minio/health/live"
    if curl -fsS --max-time 10 "http://localhost:9000/minio/health/live" >/dev/null 2>&1; then
      echo "PASS"
    else
      echo "FAIL"
      failures=$((failures + 1))
    fi
  fi
fi

if [ "$failures" -gt 0 ]; then
  echo "=== FAILED ($failures check(s)) ==="
  exit 1
fi

echo "=== All checks passed ==="
