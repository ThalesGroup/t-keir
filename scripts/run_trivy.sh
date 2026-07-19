#!/usr/bin/env bash
# Scan Python dependencies and IaC with Trivy (Docker).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TKEIR_DIR="${TKEIR_DIR:-$ROOT/tkeir}"
TRIVY_IMAGE="${TRIVY_IMAGE:-aquasec/trivy:0.58.2}"
TRIVY_SEVERITY="${TRIVY_SEVERITY:-HIGH,CRITICAL}"
REPORT_DIR="${SECURITY_REPORT_DIR:-$ROOT/reports/security}"
TRIVY_IGNORE_FILE="${TRIVY_IGNORE_FILE:-$ROOT/.trivyignore}"
# shellcheck source=docker_mount_root.sh
. "$ROOT/scripts/docker_mount_root.sh"
DOCKER_ROOT="$(_host_repo_root)"
DOCKER_REPORT_DIR="$(bash "$ROOT/scripts/docker_mount_root.sh" "${REPORT_DIR}")"

mkdir -p "$REPORT_DIR"

echo "▶ Exporting lockfiles for Trivy..."
cd "$TKEIR_DIR"
uv export --format requirements-txt --no-hashes --no-emit-project \
  -o "$REPORT_DIR/requirements.txt"
uv export --group dev --format requirements-txt --no-hashes --no-emit-project \
  -o "$REPORT_DIR/requirements-dev.txt"

TRIVY_IGNORE_ARGS=()
if [ -f "$TRIVY_IGNORE_FILE" ]; then
  TRIVY_IGNORE_ARGS=(--ignorefile "/repo/${TRIVY_IGNORE_FILE#"$ROOT"/}")
fi

echo "▶ Trivy dependency scan (runtime requirements, severity: ${TRIVY_SEVERITY})..."
docker run --rm \
  -v "${DOCKER_ROOT}:/repo:ro" \
  -v "${DOCKER_REPORT_DIR}:/report" \
  "$TRIVY_IMAGE" fs \
  --scanners vuln \
  --severity "$TRIVY_SEVERITY" \
  --exit-code 1 \
  "${TRIVY_IGNORE_ARGS[@]}" \
  --format table \
  --output /report/trivy-requirements.txt \
  /repo/reports/security/requirements.txt

echo "▶ Trivy dependency scan (dev requirements, severity: ${TRIVY_SEVERITY})..."
docker run --rm \
  -v "${DOCKER_ROOT}:/repo:ro" \
  -v "${DOCKER_REPORT_DIR}:/report" \
  "$TRIVY_IMAGE" fs \
  --scanners vuln \
  --severity "$TRIVY_SEVERITY" \
  --exit-code 1 \
  "${TRIVY_IGNORE_ARGS[@]}" \
  --format table \
  --output /report/trivy-requirements-dev.txt \
  /repo/reports/security/requirements-dev.txt

CONFIG_PATHS=()
for path in \
  "$ROOT/.github" \
  "$ROOT/.devcontainer" \
  "$ROOT/deploy" \
  "$ROOT/tkeir/runtimes/docker" \
  "$ROOT/tkeir/app/projects/template/runtimes/docker"
do
  if [ -d "$path" ] || [ -f "$path" ]; then
    CONFIG_PATHS+=("/repo/${path#"$ROOT"/}")
  fi
done

if [ "${#CONFIG_PATHS[@]}" -gt 0 ]; then
  echo "▶ Trivy config scan (Dockerfile, Compose)..."
  # Trivy's CLI does not support multiple targets for `config` scanning in a
  # single invocation. Scan each target independently.
  idx=0
  for target in "${CONFIG_PATHS[@]}"; do
    echo "  - scanning: ${target}"
    docker run --rm \
      -v "${DOCKER_ROOT}:/repo:ro" \
      -v "${DOCKER_REPORT_DIR}:/report" \
      "$TRIVY_IMAGE" config \
      --severity "$TRIVY_SEVERITY" \
      --exit-code 0 \
      --format table \
      --misconfig-scanners "dockerfile,helm,kubernetes" \
      --output "/report/trivy-config-${idx}.txt" \
      "$target"
    idx=$((idx + 1))
  done
fi

echo "✅ Trivy passed (reports in ${REPORT_DIR})"
