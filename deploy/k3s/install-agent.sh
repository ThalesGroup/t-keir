#!/usr/bin/env bash
# Join a K3s agent to an existing server.
set -euo pipefail

: "${K3S_URL:?Set K3S_URL=https://<server>:6443}"
: "${K3S_TOKEN:?Set K3S_TOKEN from /var/lib/rancher/k3s/server/node-token on the server}"

curl -sfL https://get.k3s.io | K3S_URL="${K3S_URL}" K3S_TOKEN="${K3S_TOKEN}" sh -
echo "K3s agent joined ${K3S_URL}"
