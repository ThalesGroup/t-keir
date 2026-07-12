#!/bin/bash

set -euo pipefail

if [ -z "${VESPA_NAME:-}" ]; then
    VESPA_NAME=vespa
fi

APP_DIR="$(cd "$(dirname "$0")"; pwd)/vespa_app"
REMOTE_APP_DIR="/tmp/tkeir_vespa_app_${RANDOM}"

echo "[+] Deploying Vespa application from ${APP_DIR}..."

docker cp "${APP_DIR}" "${VESPA_NAME}:${REMOTE_APP_DIR}"
docker exec "${VESPA_NAME}" bash -c \
  "vespa-deploy prepare ${REMOTE_APP_DIR} && vespa-deploy activate"

echo "[✓] Schemas deployed."
