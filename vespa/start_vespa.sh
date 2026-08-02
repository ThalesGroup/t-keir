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

# Default: never pull on start (use the local image). Opt in with VESPA_PULL=1.
VESPA_PULL="${VESPA_PULL:-0}"

echo "[+] Ensuring Vespa container '${VESPA_NAME}' is running..."

if docker ps -a --format '{{.Names}}' | grep -qx "${VESPA_NAME}"; then
    if docker ps --format '{{.Names}}' | grep -qx "${VESPA_NAME}"; then
        echo "[✓] Vespa container already running on http://localhost:8080"
        exit 0
    fi
    echo "[+] Starting existing Vespa container..."
    docker start "${VESPA_NAME}" >/dev/null
else
    if ! docker image inspect "${VESPA_IMAGE}" >/dev/null 2>&1; then
        if [[ "${VESPA_PULL}" == "1" ]]; then
            echo "[+] Pulling ${VESPA_IMAGE}…"
            docker pull "${VESPA_IMAGE}"
        else
            echo "[!] Local image '${VESPA_IMAGE}' not found." >&2
            echo "    Pull once with:  make pull-vespa" >&2
            echo "    Or:              VESPA_PULL=1 make start" >&2
            exit 1
        fi
    else
        echo "[i] Using local image ${VESPA_IMAGE} (no pull)."
    fi
    echo "[+] Creating Vespa container..."
    docker run -d --name "${VESPA_NAME}" \
      -p 8080:8080 -p 19071:19071 -p 19050:19050 \
      -v "${VESPA_VOLUME}" \
      "${VESPA_IMAGE}"
fi

echo "[✓] Vespa started on http://localhost:8080 (config server: http://localhost:19071)"
