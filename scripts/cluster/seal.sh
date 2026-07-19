#!/usr/bin/env bash
# Seal a Kubernetes Secret with sealed-secrets (kubeseal).
set -euo pipefail

: "${SECRET_FILE:?Set SECRET_FILE=path/to/secret.yaml}"
OUT="${OUT:-${SECRET_FILE%.yaml}.sealed.yaml}"
CONTROLLER_NAMESPACE="${SEALED_SECRETS_NS:-kube-system}"
CONTROLLER_NAME="${SEALED_SECRETS_NAME:-sealed-secrets}"

command -v kubeseal >/dev/null 2>&1 || {
  echo "kubeseal required: https://github.com/bitnami-labs/sealed-secrets" >&2
  exit 1
}

kubeseal \
  --controller-namespace "${CONTROLLER_NAMESPACE}" \
  --controller-name "${CONTROLLER_NAME}" \
  --format yaml \
  < "${SECRET_FILE}" > "${OUT}"

echo "Sealed → ${OUT}"
