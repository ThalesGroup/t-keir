# deploy/

Platform packaging for T-KEIR installation profiles P1–P4.

| Path | Purpose |
|------|---------|
| `versions.lock.yaml` | Third-party image/chart pins (digest + update command) |
| `compose/` | Docker Compose stack (Workstream A) |
| `images/` | Dockerfiles + `docker-bake.hcl` — shared `tkeir-lib`, then thin services (`make images`) |

| `charts/` | Helm umbrella + sub-charts — `make helm-lint` / `cluster-install PROFILE=k8s-dev` |
| `keycloak/` | Realm `tkeir` export + config-cli (Workstream K) |
| `k3s/` | Hardened K3s + Lima macOS path (Workstream F) |
| `kubeflow/` | Pipelines standalone + Model Registry (Workstream G) |
| `policies/` | Network / app authz / image verify bundles |
| `spire/` | SPIRE server/agent configs for agent SPIFFE (ADR-0008) |

Canonical docs: [tkeir/docs/deployment/](../tkeir/docs/deployment/index.md).

Image registry:

- **Local / Compose default:** `local` (`make images` → `local/tkeir-*:…`)
- **Publish / CI:** `ghcr.io/thalesgroup/t-keir`
  (`make images-push IMAGE_REGISTRY=ghcr.io/thalesgroup/t-keir`)
