# Secure Kubernetes (P3)

> **Status:** Progressive hardening — SPIRE for **agents**
>; JWT + correlation for
> RAG/ingest until mesh expansion.

P3 adds stricter **values presets** and optional cluster controls. Human
identity uses Keycloak JWTs; agent workloads carry SPIFFE IDs for mastering.

## What P3 includes (now)

| Control | Mechanism |
|---------|-----------|
| Governor enforce | `values-secure.yaml` → `governor.mode: enforce` |
| Audit + WORM | `audit.enabled: true` |
| HMI auth | `hmi.env.AUTH_ENABLED: "true"` |
| Staging env | `global.env: staging` |
| Policy bundle | `deploy/policies/app/tkeir-intents.rego` (agent SPIFFE when enforce) |
| Agent SPIFFE | Compose `spire` / cluster SPIRE Agent socket → `SPIFFE_MODE=workload` |

## What P3 explicitly excludes (this stage)

| Item | Reason |
|------|--------|
| Full-mesh SPIFFE for every service | Agent path first; RAG/ingest later |
| Full default-deny NetworkPolicy mesh | Needs per-service allow rules; tracked separately |
| cert-manager / sealed-secrets | Installer detection (Phase 7) |

## Install

```bash
make k3d-up
make cluster-install PROFILE=k8s-secure
make smoke-test SMOKE_TARGET_URL=http://localhost:8090 # port-forward api first
```

Linux hardened path (future):

```bash
make k3s-server # Linux
make lima-k3s-up # macOS → Lima VM → K3s + Cilium
make k3s-check # kube-bench (digest-pinned image)
```

See [macOS notes](macos.md) for Cilium / Lima and flannel fallback.

## Related

- [Deployment profiles](index.md)
- [SPIRE / SPIFFE](spire.md)
- [Governor](governor.md)
