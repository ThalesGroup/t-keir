#!/usr/bin/env bash
# Rebuild and recreate the devcontainer.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "▶ Rebuilding devcontainer (no cache, replace existing)..."
devcontainer up --workspace-folder "${ROOT}" --remove-existing-container --build-no-cache
echo "✅ Devcontainer ready — enter with: bash .devcontainer/enter-devcontainer.sh"
