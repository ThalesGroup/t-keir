#!/usr/bin/env bash
# Register SPIFFE entries for tkeir-agent workloads (ADR-0008).
# Intended to run against a live spire-server after the agent has joined.
set -euo pipefail

SPIRE_SERVER="${SPIRE_SERVER:-spire-server:8081}"
TRUST_DOMAIN="${SPIFFE_TRUST_DOMAIN:-tkeir.local}"
BIN="${SPIRE_SERVER_BIN:-/opt/spire/bin/spire-server}"

echo "Registering agent workload entries on ${SPIRE_SERVER} (trust=${TRUST_DOMAIN})"

# Parent entry for the SPIRE agent node (join_token path is operator-driven).
# Workload entries use unix uid selector as a Compose-friendly default.
# Parent matches `make spire-up` token generate -spiffeID.
for name in tkeir-agent researcher supervisor writer; do
  "${BIN}" entry create \
    -socketPath /tmp/spire-server/private/api.sock \
    -spiffeID "spiffe://${TRUST_DOMAIN}/agent/${name}" \
    -parentID "spiffe://${TRUST_DOMAIN}/spire-agent" \
    -selector unix:uid:0 \
    -ttl 3600 \
    || true
done

echo "Done. Set SPIFFE_MODE=workload and SPIFFE_ENDPOINT_SOCKET on tkeir-agent."
