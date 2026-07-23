# macOS deployment notes

Apple Silicon and Intel Macs are first-class for **P0–P2**.

## P0 / P1

- Docker Desktop, OrbStack, or Colima.
- Run **Ollama on the host** for Metal acceleration; point containers at
  `http://host.docker.internal:11434` (same as the
  [dev container](../devcontainer.md)).
- Compose profile `core` (+ `auth`) must work on `linux/arm64` images.

## P3 — Cilium caveat

Cilium requires Linux eBPF and **cannot** run against the macOS kernel.

Use Lima (`deploy/k3s/macos-lima/`, target `make lima-k3s-up`):

1. Ubuntu LTS VM (`vmType: vz`, ≥ 4 CPU / 8 GiB).
2. Hardened K3s + Cilium inside the VM.
3. kubeconfig exported to the host; ports 80/443/6443 forwarded.
4. Host Ollama reachable as `host.lima.internal:11434`.

**Fallback:** K3s default flannel. Embedded NetworkPolicy enforcement still
applies; Hubble/L7 is unavailable. The installer must print this maturity
downgrade explicitly.
