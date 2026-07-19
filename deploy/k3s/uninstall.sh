#!/usr/bin/env bash
# Uninstall K3s (server or agent).
set -euo pipefail

if [ -x /usr/local/bin/k3s-uninstall.sh ]; then
  /usr/local/bin/k3s-uninstall.sh
elif [ -x /usr/local/bin/k3s-agent-uninstall.sh ]; then
  /usr/local/bin/k3s-agent-uninstall.sh
else
  echo "No k3s uninstall script found" >&2
  exit 1
fi
