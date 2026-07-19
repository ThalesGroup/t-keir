#!/usr/bin/env bash
# Stop / delete the T-KEIR Lima VM.
set -euo pipefail
NAME="${LIMA_NAME:-tkeir-k3s}"
command -v limactl >/dev/null 2>&1 || exit 0
limactl stop "${NAME}" 2>/dev/null || true
if [ "${DELETE_VM:-0}" = "1" ]; then
  limactl delete -f "${NAME}" 2>/dev/null || true
fi
