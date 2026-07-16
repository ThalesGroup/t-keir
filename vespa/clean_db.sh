#!/bin/bash
set -euo pipefail

VESPA_NAME="${VESPA_NAME:-vespa}"
VESPA_VOLUME_MOUNT="${VESPA_VOLUME:-vespa_data:/opt/vespa/var}"
VESPA_VOLUME_NAME="${VESPA_VOLUME_MOUNT%%:*}"

echo "[+] Stopping Vespa container '${VESPA_NAME}'..."
docker stop "${VESPA_NAME}" >/dev/null 2>&1 || true
docker rm "${VESPA_NAME}" >/dev/null 2>&1 || true

if [[ "${VESPA_VOLUME_NAME}" == /* ]]; then
    echo "[i] Bind mount '${VESPA_VOLUME_MOUNT}' — host path '${VESPA_VOLUME_NAME}' is not removed."
else
    echo "[+] Removing Vespa data volume '${VESPA_VOLUME_NAME}'..."
    docker volume rm "${VESPA_VOLUME_NAME}" >/dev/null 2>&1 || true
fi

echo "[✓] Vespa database wiped. Run 'make bootstrap' to start fresh."
