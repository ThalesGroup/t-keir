#!/usr/bin/env bash
set -euo pipefail
CLUSTER_NAME="${CLUSTER_NAME:-tkeir}"
REGISTRY_NAME="${REGISTRY_NAME:-tkeir-registry}"
DELETE_REGISTRY="${DELETE_REGISTRY:-0}"

k3d cluster delete "${CLUSTER_NAME}" || true
if [[ "${DELETE_REGISTRY}" == "1" ]]; then
  k3d registry delete "${REGISTRY_NAME}" || true
fi
echo "k3d cluster ${CLUSTER_NAME} deleted"
