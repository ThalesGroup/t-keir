#!/usr/bin/env bash
# Scan Python dependencies with OWASP Dependency-Check (Docker).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TKEIR_DIR="${TKEIR_DIR:-$ROOT/tkeir}"
OWASP_DC_IMAGE="${OWASP_DC_IMAGE:-owasp/dependency-check:12.1.0}"
OWASP_DC_FAIL_CVSS="${OWASP_DC_FAIL_CVSS:-7}"
REPORT_DIR="${OWASP_DC_REPORT_DIR:-$ROOT/reports/dependency-check}"
DATA_DIR="${OWASP_DC_DATA_DIR:-$ROOT/.cache/dependency-check}"
NOUPDATE="${OWASP_DC_NOUPDATE:-}"
# shellcheck source=docker_mount_root.sh
. "$ROOT/scripts/docker_mount_root.sh"
DOCKER_ROOT="$(_host_repo_root)"
DOCKER_REPORT_DIR="$(bash "$ROOT/scripts/docker_mount_root.sh" "${REPORT_DIR}")"
DOCKER_DATA_DIR="$(bash "$ROOT/scripts/docker_mount_root.sh" "${DATA_DIR}")"

mkdir -p "$REPORT_DIR" "$DATA_DIR" "$ROOT/reports/security"

echo "▶ Exporting requirements for Dependency-Check..."
cd "$TKEIR_DIR"
uv export --format requirements-txt --no-hashes --no-emit-project \
  -o "$ROOT/reports/security/requirements.txt"
uv export --group dev --format requirements-txt --no-hashes --no-emit-project \
  -o "$ROOT/reports/security/requirements-dev.txt"

NVD_ARGS=()
if [ -n "$NOUPDATE" ]; then
  NVD_ARGS=(--noupdate)
fi

DOCKER_ENV=()
if [ -n "${NVD_API_KEY:-}" ]; then
  DOCKER_ENV+=(-e "NVD_API_KEY=${NVD_API_KEY}")
fi

echo "▶ OWASP Dependency-Check (failOnCVSS >= ${OWASP_DC_FAIL_CVSS})..."
docker run --rm \
  ${DOCKER_ENV[@]+"${DOCKER_ENV[@]}"} \
  -v "${DOCKER_ROOT}:/src:ro" \
  -v "${DOCKER_REPORT_DIR}:/report" \
  -v "${DOCKER_DATA_DIR}:/usr/share/dependency-check/data" \
  "$OWASP_DC_IMAGE" \
  --scan /src/tkeir/pyproject.toml \
  --scan /src/tkeir/uv.lock \
  --scan /src/reports/security/requirements.txt \
  --scan /src/reports/security/requirements-dev.txt \
  --project t-keir \
  --out /report \
  --format JSON \
  --format HTML \
  --failOnCVSS "$OWASP_DC_FAIL_CVSS" \
  ${NVD_ARGS[@]+"${NVD_ARGS[@]}"}

echo "✅ OWASP Dependency-Check passed (reports in ${REPORT_DIR})"
