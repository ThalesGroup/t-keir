# Deployment profiles

T-KEIR installs **progressively**. Prefer the didactic path
**[Zero to Hero](../zero_to_hero.md)**; this page is the profile matrix.

Each profile is one documented command path away; higher profiles reuse the same
charts/Compose services with stricter value presets.

| Profile | Runtime | What you get |
|---------|---------|--------------|
| **P0** `dev-local` | `uv` + Docker (+ [devcontainer](../devcontainer.md)) | `make setup` → `bootstrap` → `index` → `rag` + HMI; Vespa streaming group **`dev@tkeir`** |
| **P1** `compose` | Docker Compose | Full stack + Keycloak (`auth`); JWT → per-user Vespa space — [Compose](compose.md) |
| **P2** `k8s-dev` | k3d / any cluster | Umbrella Helm, permissive security — [Kubernetes (dev)](k8s.md) |
| **P3** `k8s-secure` | Hardened K3s | Governor enforce, audit, auth on; agent SPIFFE via SPIRE — [Secure cluster](k8s-secure.md) |
| **P4** `platform` | P3 + platform add-ons | Kubeflow Pipelines standalone + Model Registry, governor enforced, WORM retention, evidence automation |

## Rules

- **Do not break P0.** Contributor paths and CLI names stay stable.
- **macOS** is first-class for P0–P2. For P3, use [Lima + K3s](macos.md) (Cilium
  needs Linux eBPF) or accept the flannel maturity downgrade.
- **On-demand install:** the installer (Phase 7) detects existing Prometheus,
  cert-manager, IdP, GPU, object-lock buckets, etc., and only deploys missing
  pieces. **SPIRE** is required for the **agents** path; optional
  for RAG-only deployments.
- **Pins:** `deploy/versions.lock.yaml`.

## Control plane docs

| Topic | Doc |
|-------|-----|
| Environment variables | [Environment variables](environment.md) |
| Hybrid demo (tmux launcher) | [start_services.sh](start_services.md) |
| ActionRecord hot store + WORM | [Audit store](audit.md) |
| Kill switch, budgets, approvals, tokens | [Governor](governor.md) |
| Agent workload identity | [SPIRE / SPIFFE](spire.md) |
| Ingest pipeline | [Ingest](ingest.md) |

## Related design

- [Identity of Action](../regularity-component/action-identiy.md)
- [Mastering of Action](../regularity-component/action-mastering.md)
- [Security](../security.md)
