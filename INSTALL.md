# Installation profiles

This file is the **root pointer** to the canonical guides.

**Start here:** [Zero to Hero — install and use from dev to prod](docs/zero_to_hero.md)
(MkDocs: *Zero to Hero*).

| Profile | Name | How to start | Audience |
|---------|------|--------------|----------|
| **P0** | `dev-local` | [Zero to Hero §3–4](docs/zero_to_hero.md#3-p0-dev-local--first-pipeline) — `make setup` … `make rag` + HMI | Contributors |
| **P1** | `compose` | [Zero to Hero §5](docs/zero_to_hero.md#5-p1-docker-compose-full-demo) / [Compose](docs/deployment/compose.md) | Full-stack demo |
| **P2** | `k8s-dev` | [Zero to Hero §6](docs/zero_to_hero.md#6-p2-kubernetes-dev-k3d) / [Kubernetes](docs/deployment/k8s.md) | Chart / integration |
| **P3** | `k8s-secure` | [Zero to Hero §7](docs/zero_to_hero.md#7-p3-secure-cluster) / [Secure cluster](docs/deployment/k8s-secure.md) | Pre-prod / prod |
| **P4** | `platform` | [Zero to Hero §8](docs/zero_to_hero.md#8-p4-platform--evidence) | Regulated production |

**Canonical docs:** [docs/deployment/](docs/deployment/index.md) (MkDocs: Deployment).

**P0 stays the same Makefile path** (`setup` → `bootstrap` → `index` → `rag`).
Vespa is streaming-mode with local group **`dev@tkeir`**; Keycloak isolation
starts at P1 — see [Zero to Hero §4–5](docs/zero_to_hero.md#4-p0--vespa-rag--hmi).
Keep using the [dev container](docs/devcontainer.md) when you prefer that.

Version pins for third-party images and charts live in
[`deploy/versions.lock.yaml`](deploy/versions.lock.yaml).

**P4 / regulated demos:** run `make audit-compliance` after evidence packs —
see [EU Compliance OPA Audit](docs/compliance/eu-audit.md).
