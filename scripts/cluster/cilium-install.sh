#!/usr/bin/env bash
# Install Cilium via Helm (Linux / Lima). Not supported on bare macOS Docker Desktop CNI.
set -euo pipefail

CILIUM_VERSION="${CILIUM_VERSION:-1.17.2}"
NAMESPACE="${CILIUM_NAMESPACE:-kube-system}"

command -v helm >/dev/null 2>&1 || { echo "helm required"; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "kubectl required"; exit 1; }

helm repo add cilium https://helm.cilium.io/ >/dev/null
helm repo update cilium >/dev/null
helm upgrade --install cilium cilium/cilium \
  --version "${CILIUM_VERSION}" \
  --namespace "${NAMESPACE}" \
  --set hubble.relay.enabled=true \
  --set hubble.ui.enabled=false \
  --set kubeProxyReplacement=true \
  --wait

kubectl -n "${NAMESPACE}" rollout status ds/cilium --timeout=300s
echo "✅ Cilium ${CILIUM_VERSION} installed"
