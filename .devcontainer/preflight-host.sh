#!/usr/bin/env bash
# Runs on the host before the devcontainer starts (initializeCommand).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required for Trivy/OWASP scans and the devcontainer."
  echo "Install: https://docs.docker.com/get-docker/"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required (docker compose)."
  exit 1
fi

echo "✅ Devcontainer preflight OK"
