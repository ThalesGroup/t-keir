#!/bin/bash
set -euo pipefail

VESPA_NAME="${VESPA_NAME:-vespa}"
VESPA_VOLUME="${VESPA_VOLUME:-vespa_data}"

echo "[+] Stopping Vespa container '${VESPA_NAME}'..."
docker stop "${VESPA_NAME}" >/dev/null 2>&1 || true
docker rm "${VESPA_NAME}" >/dev/null 2>&1 || true

echo "[+] Removing Vespa data volume '${VESPA_VOLUME}'..."
docker volume rm "${VESPA_VOLUME}" >/dev/null 2>&1 || true

echo "[✓] Vespa database wiped. Run 'make bootstrap' to start fresh."
