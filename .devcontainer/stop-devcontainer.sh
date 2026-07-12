#!/usr/bin/env bash
# Stop the dev workstation container.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT="${DEVCONTAINER_PROJECT_NAME:-t_keir_devcontainer}"

echo "▶ Stopping devcontainer compose project (${PROJECT})..."
docker compose -p "${PROJECT}" -f "${ROOT}/.devcontainer/docker-compose.yml" down "$@"
echo "✅ Dev container stopped"
