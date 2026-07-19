# Secure Kubernetes (P3)

> **Status:** Progressive hardening — **no SPIRE** during software development
> (see [ADR-0004](../adr/0004-defer-spire.md)).

P3 adds stricter **values presets** and optional cluster controls. Identity and
traceability rely on Keycloak JWTs, W3C correlation IDs, and the audit hot store —
not SPIFFE agents.

## What P3 includes (now)

| Control | Mechanism |
|---------|-----------|
| Governor enforce | `values-secure.yaml` → `governor.mode: enforce` |
| Audit + WORM | `audit.enabled: true` |
| HMI auth | `hmi.env.AUTH_ENABLED: "true"` |
| Staging env | `global.env: staging` |
| Policy bundle | `deploy/policies/app/tkeir-intents.rego` (stub; governor evaluates in-process) |

## What P3 explicitly excludes (this stage)

| Item | Reason |
|------|--------|
| **SPIRE / SPIFFE** | No agents; JWT + correlation + ActionRecord suffice for dev/pre-prod |
| Full default-deny NetworkPolicy mesh | Needs per-service allow rules; tracked separately |
| cert-manager / sealed-secrets | Installer detection (Phase 7) |

## Install

```bash
make k3d-up
make cluster-install PROFILE=k8s-secure
make smoke-test SMOKE_TARGET_URL=http://localhost:8090   # port-forward api first
```

Linux hardened path (future):

```bash
make k3s-server          # Linux
make lima-k3s-up         # macOS → Lima VM → K3s + Cilium
make k3s-check           # kube-bench (digest-pinned image)
```

See [macOS notes](macos.md) for Cilium / Lima and flannel fallback.

## Related

- [Deployment profiles](index.md)
- [ADR-0004 — Defer SPIRE](../adr/0004-defer-spire.md)
- [Governor](governor.md)
