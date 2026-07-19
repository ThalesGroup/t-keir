#!/usr/bin/env bash
# Install a hardened single-node K3s server (Linux). SPIRE is NOT installed (ADR-0004).
set -euo pipefail

# CIS-oriented defaults: secrets encryption, audit log path, protect kernel defaults.
# When Cilium is selected: flannel disabled + traefik disabled.
USE_CILIUM="${USE_CILIUM:-1}"
K3S_VERSION="${K3S_VERSION:-}"
INSTALL_K3S_EXEC=(
  --secrets-encryption
  --protect-kernel-defaults
  --write-kubeconfig-mode=600
  --kube-apiserver-arg=audit-log-path=/var/lib/rancher/k3s/server/logs/audit.log
  --kube-apiserver-arg=audit-log-maxage=30
  --kube-apiserver-arg=audit-log-maxbackup=10
  --kube-apiserver-arg=audit-log-maxsize=100
)

if [ "${USE_CILIUM}" = "1" ]; then
  INSTALL_K3S_EXEC+=(
    --flannel-backend=none
    --disable-network-policy
    --disable=traefik
  )
fi

export INSTALL_K3S_EXEC="${INSTALL_K3S_EXEC[*]}"
if [ -n "${K3S_VERSION}" ]; then
  export INSTALL_K3S_VERSION="${K3S_VERSION}"
fi

curl -sfL https://get.k3s.io | sh -

echo "K3s server installed. kubeconfig: /etc/rancher/k3s/k3s.yaml"
echo "Next: make cilium-install (if USE_CILIUM=1), then make cluster-install PROFILE=k8s-secure"
