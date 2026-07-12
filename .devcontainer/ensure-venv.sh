#!/usr/bin/env bash
# Remove a host-created or broken tkeir/.venv before uv sync in the devcontainer.
set -euo pipefail

VENV_DIR="${1:-/workspace/tkeir/.venv}"

if [[ ! -d "${VENV_DIR}" ]]; then
  exit 0
fi

venv_is_usable() {
  local python="${VENV_DIR}/bin/python"
  [[ -x "${python}" ]] || return 1
  "${python}" -c "import sys; assert sys.version_info[:2] == (3, 11)" 2>/dev/null
}

if venv_is_usable; then
  exit 0
fi

echo "▶ Removing incompatible virtualenv at ${VENV_DIR}..."
chmod -R u+w "${VENV_DIR}" 2>/dev/null || true
rm -rf "${VENV_DIR}"
