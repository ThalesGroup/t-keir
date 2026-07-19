#!/usr/bin/env bash
# helm upgrade --install umbrella with profile preset.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CHART="${ROOT}/deploy/charts/tkeir"
PROFILE="${PROFILE:-k8s-dev}"
RELEASE="${RELEASE:-tkeir}"
NAMESPACE="${NAMESPACE:-tkeir}"

case "${PROFILE}" in
  k8s-dev|dev) VALUES="${CHART}/values-dev.yaml" ;;
  k8s-secure|secure) VALUES="${CHART}/values-secure.yaml" ;;
  platform) VALUES="${CHART}/values-platform.yaml" ;;
  *) echo "Unknown PROFILE=${PROFILE} (k8s-dev|k8s-secure|platform)" >&2; exit 2 ;;
esac

helm dependency update "${CHART}"
kubectl get ns "${NAMESPACE}" >/dev/null 2>&1 || kubectl create ns "${NAMESPACE}"
helm upgrade --install "${RELEASE}" "${CHART}" \
  --namespace "${NAMESPACE}" \
  -f "${VALUES}" \
  --atomic \
  --wait \
  --timeout 15m \
  "$@"

kubectl annotate release.v1.helm.sh/"${RELEASE}" \
  -n "${NAMESPACE}" \
  tkeir.io/installed-by=tkeir-installer --overwrite 2>/dev/null || true

echo "Installed ${RELEASE} in ${NAMESPACE} (PROFILE=${PROFILE})"
helm status "${RELEASE}" -n "${NAMESPACE}"
