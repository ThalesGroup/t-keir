#!/usr/bin/env bash
# Repository secret hygiene: tracked .env guard + pattern scan.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGED="${CHECK_SECRETS_STAGED:-0}"
PY_ARGS=()

if [[ "${STAGED}" == "1" ]]; then
  PY_ARGS+=(--staged)
fi

cd "${ROOT}"

if git ls-files --error-unmatch .env 2>/dev/null; then
  echo "ERROR: .env is tracked by git. Remove it with: git rm --cached .env" >&2
  exit 1
fi

if git ls-files --error-unmatch deploy/compose/.env 2>/dev/null; then
  echo "ERROR: deploy/compose/.env is tracked by git." >&2
  echo "Remove it with: git rm --cached deploy/compose/.env" >&2
  exit 1
fi

if [[ -x "${ROOT}/tkeir/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/tkeir/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
else
  echo "python3 is required for scripts/scan_secrets.py" >&2
  exit 1
fi

exec "${PYTHON}" "${ROOT}/scripts/scan_secrets.py" ${PY_ARGS[@]+"${PY_ARGS[@]}"}
