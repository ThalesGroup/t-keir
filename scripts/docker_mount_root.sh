#!/usr/bin/env bash
# Resolve host filesystem paths for docker -v when running inside a devcontainer.
set -euo pipefail

_repo_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

_host_repo_root() {
  local root="$(_repo_root)"

  if [[ -n "${LOCAL_WORKSPACE_FOLDER:-}" ]]; then
    echo "${LOCAL_WORKSPACE_FOLDER}"
    return
  fi

  if [[ -n "${TKEIR_HOST_WORKSPACE:-}" ]]; then
    echo "${TKEIR_HOST_WORKSPACE}"
    return
  fi

  if [[ ! -f /.dockerenv ]] || ! command -v docker >/dev/null 2>&1; then
    echo "${root}"
    return
  fi

  local project="${DEVCONTAINER_PROJECT_NAME:-t_keir_devcontainer}"
  local container="${DEVCONTAINER_SERVICE_CONTAINER:-${project}-dev-1}"
  local source=""
  source="$(docker inspect "${container}" \
    --format '{{range .Mounts}}{{if eq .Destination "/workspace"}}{{.Source}}{{end}}{{end}}' \
    2>/dev/null || true)"
  if [[ -n "${source}" ]]; then
    echo "${source}"
    return
  fi

  echo "${root}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  root="$(_repo_root)"
  host_root="$(_host_repo_root)"
  target="${1:-${root}}"
  if [[ "${target}" == "${root}"* ]]; then
    echo "${host_root}${target#"${root}"}"
  else
    echo "${target}"
  fi
fi
