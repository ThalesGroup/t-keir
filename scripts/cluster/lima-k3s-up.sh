#!/usr/bin/env bash
# Start Lima VM and install hardened K3s + optional Cilium inside the guest.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
NAME="${LIMA_NAME:-tkeir-k3s}"
TEMPLATE="${ROOT}/deploy/k3s/macos-lima/lima.yaml"

command -v limactl >/dev/null 2>&1 || {
  echo "limactl required: https://lima-vm.io/" >&2
  exit 1
}

if ! limactl list -q | grep -qx "${NAME}"; then
  limactl start --name="${NAME}" "${TEMPLATE}"
else
  limactl start "${NAME}" || true
fi

echo "Installing K3s inside Lima VM ${NAME}..."
limactl shell "${NAME}" sudo bash -s -- <<'EOS'
set -euo pipefail
export USE_CILIUM=1
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--secrets-encryption --protect-kernel-defaults --flannel-backend=none --disable-network-policy --disable=traefik --write-kubeconfig-mode=644" sh -
EOS

echo "Exporting kubeconfig to ~/.kube/config.tkeir-lima"
mkdir -p "${HOME}/.kube"
limactl shell "${NAME}" sudo cat /etc/rancher/k3s/k3s.yaml \
  | sed "s/127.0.0.1/127.0.0.1/g" > "${HOME}/.kube/config.tkeir-lima"
echo "export KUBECONFIG=${HOME}/.kube/config.tkeir-lima"
echo "Next: make cilium-install && make cluster-install PROFILE=k8s-secure"
echo "Ollama on host: OLLAMA_BASE_URL=http://host.lima.internal:11434"
