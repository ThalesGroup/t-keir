#!/bin/bash

set -euo pipefail

if [ -z "${VESPA_NAME:-}" ]; then
    VESPA_NAME=vespa
fi

if [ -z "${VESPA_VOLUME:-}" ]; then
    VESPA_VOLUME=vespa_data:/opt/vespa/var
fi

if [ -z "${VESPA_IMAGE:-}" ]; then
    VESPA_IMAGE=vespaengine/vespa
fi

echo "[+] Ensuring Vespa container '${VESPA_NAME}' is running..."

if docker ps -a --format '{{.Names}}' | grep -qx "${VESPA_NAME}"; then
    if docker ps --format '{{.Names}}' | grep -qx "${VESPA_NAME}"; then
        echo "[✓] Vespa container already running on http://localhost:8080"
        exit 0
    fi
    echo "[+] Starting existing Vespa container..."
    docker start "${VESPA_NAME}" >/dev/null
else
    echo "[+] Pulling ${VESPA_IMAGE} (if needed)…"
    docker pull "${VESPA_IMAGE}" >/dev/null
    echo "[+] Creating Vespa container..."
    docker run -d --name "${VESPA_NAME}" \
      -p 8080:8080 -p 19071:19071 -p 19050:19050 \
      -v "${VESPA_VOLUME}" \
      "${VESPA_IMAGE}"
fi

echo "[✓] Vespa started on http://localhost:8080 (config server: http://localhost:19071)"
