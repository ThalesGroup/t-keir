# Kubernetes development (P2)

Umbrella Helm chart under `deploy/charts/tkeir` with sub-charts:

| Chart | Role |
|-------|------|
| `tkeir-vespa` | Single-node StatefulSet + PVC (`resourceProfile`) |
| `tkeir-api` | RAG Deployment (`tkeir-rag`) |
| `tkeir-hmi` | Next.js HMI |
| `tkeir-indexer` | Suspended CronJob (set `schedule` to enable) |
| `tkeir-inference` | `mode: external\|ollama\|vllm` → existing env contract |
| `tkeir-lib` | Library (labels, probes, securityContext) |

## Quick path

```bash
make k3d-up
# Load or push images into k3d registry (localhost:5001)
make cluster-install PROFILE=k8s-dev
helm test tkeir -n tkeir   # or: make helm-test
```

Disable one component:

```bash
helm upgrade tkeir deploy/charts/tkeir -n tkeir -f deploy/charts/tkeir/values-dev.yaml \
  --set hmi.enabled=false
```

## Value presets

| File | Profile |
|------|---------|
| `values-dev.yaml` | P2 `k8s-dev` |
| `values-secure.yaml` | P3 placeholders |
| `values-platform.yaml` | P4 placeholders |

## macOS

k3d works with Docker Desktop, OrbStack, or Colima. Point
`api.env.OLLAMA_BASE_URL` at the host (default
`http://host.docker.internal:11434`).

See also [Compose (P1)](compose.md) and [Secure cluster (P3)](k8s-secure.md).
