#!/usr/bin/env bash
# Start the devcontainer (if needed) and open an interactive shell, or run a command.
#
# Usage (from repository root or any path):
#   bash .devcontainer/enter-devcontainer.sh
#   bash .devcontainer/enter-devcontainer.sh --build
#   bash .devcontainer/enter-devcontainer.sh -- make ci
#   bash .devcontainer/enter-devcontainer.sh --rebuild
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_PROJECT="${DEVCONTAINER_PROJECT_NAME:-t_keir_devcontainer}"
COMPOSE_FILE="${ROOT}/.devcontainer/docker-compose.yml"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options] [-- command [args...]]

Start the T-KEIR devcontainer and open a shell in /workspace, or run a single command.

Options:
  --build      Rebuild the image before starting (docker compose build)
  --rebuild    Destroy and recreate the container (see rebuild-devcontainer.sh)
  -h, --help   Show this help

Examples:
  $(basename "$0")
  $(basename "$0") --build
  $(basename "$0") -- make setup
  $(basename "$0") -- make ci

Requires Docker. Prefers the devcontainer CLI (npm install -g @devcontainers/cli).
EOF
}

BUILD=false
REBUILD=false
EXEC_CMD=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build)
      BUILD=true
      shift
      ;;
    --rebuild)
      REBUILD=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      EXEC_CMD=("$@")
      break
      ;;
    -*)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      EXEC_CMD=("$@")
      break
      ;;
  esac
done

if $REBUILD; then
  exec bash "${ROOT}/.devcontainer/rebuild-devcontainer.sh"
fi

bash "${ROOT}/.devcontainer/preflight-host.sh"

run_with_devcontainer_cli() {
  local up_args=(--workspace-folder "${ROOT}")
  if $BUILD; then
    up_args+=(--build-no-cache)
  fi

  echo "▶ Starting devcontainer..."
  devcontainer up "${up_args[@]}"

  if [[ ${#EXEC_CMD[@]} -eq 0 ]]; then
    echo "▶ Opening shell in /workspace (exit to return to host)..."
    devcontainer exec --workspace-folder "${ROOT}" bash -l
  else
    devcontainer exec --workspace-folder "${ROOT}" -- "${EXEC_CMD[@]}"
  fi
}

run_with_docker_compose() {
  local compose=(docker compose -p "${COMPOSE_PROJECT}" -f "${COMPOSE_FILE}")

  if $BUILD; then
    echo "▶ Building devcontainer image..."
    "${compose[@]}" build
  fi

  echo "▶ Starting devcontainer..."
  "${compose[@]}" up -d

  echo "▶ Ensuring Python environment..."
  "${compose[@]}" exec -T dev bash -c \
    'bash .devcontainer/ensure-venv.sh; [[ -x /workspace/tkeir/.venv/bin/python ]] || bash .devcontainer/post-create.sh'

  if [[ ${#EXEC_CMD[@]} -eq 0 ]]; then
    echo "▶ Opening shell in /workspace (exit to return to host)..."
    "${compose[@]}" exec -it dev bash -l
  else
    "${compose[@]}" exec -it dev "${EXEC_CMD[@]}"
  fi
}

if command -v devcontainer >/dev/null 2>&1; then
  run_with_devcontainer_cli
else
  echo "note: devcontainer CLI not found — using docker compose fallback" >&2
  echo "      install for full devcontainer.json lifecycle: npm install -g @devcontainers/cli" >&2
  echo "" >&2
  run_with_docker_compose
fi
