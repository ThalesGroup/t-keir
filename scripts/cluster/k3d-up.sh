#!/usr/bin/env bash
# Create a local k3d cluster with registry and port mappings (P2).
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-tkeir}"
REGISTRY_NAME="${REGISTRY_NAME:-tkeir-registry}"
REGISTRY_PORT="${REGISTRY_PORT:-5001}"
K3D_API_PORT="${K3D_API_PORT:-6550}"

if ! command -v k3d >/dev/null 2>&1; then
  echo "k3d is required: https://k3d.io/" >&2
  exit 1
fi

if ! k3d registry list 2>/dev/null | grep -q "${REGISTRY_NAME}"; then
  k3d registry create "${REGISTRY_NAME}" --port "${REGISTRY_PORT}"
fi

if k3d cluster list -o json 2>/dev/null | grep -q "\"name\":\"${CLUSTER_NAME}\""; then
  echo "Cluster ${CLUSTER_NAME} already exists"
else
  k3d cluster create "${CLUSTER_NAME}" \
    --registry-use "k3d-${REGISTRY_NAME}:${REGISTRY_PORT}" \
    --api-port "127.0.0.1:${K3D_API_PORT}" \
    -p "80:80@loadbalancer" \
    -p "443:443@loadbalancer" \
    --agents 0
fi

kubectl cluster-info
echo "k3d ready. Local registry: localhost:${REGISTRY_PORT}"
echo "Push images: docker tag … localhost:${REGISTRY_PORT}/tkeir-api:dev && docker push …"
