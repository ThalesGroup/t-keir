# Container images

| Target | Dockerfile | Entrypoint |
|--------|------------|------------|
| `tkeir-api` | `Dockerfile.tkeir-api` | `tkeir-rag` (:8090) |
| `tkeir-indexer` | `Dockerfile.tkeir-indexer` | `entrypoint-indexer.sh` (OCR) |
| `tkeir-indexer-slim` | same, `INSTALL_OCR=0` | same without Tesseract |
| `tkeir-hmi` | `Dockerfile.tkeir-hmi` | Next.js standalone (:3000) |
| `tkeir-mcp` | `Dockerfile.tkeir-mcp` | `tkeir-mcp` (:8093) |
| `tkeir-agent` | `Dockerfile.tkeir-agent` | `tkeir-agent` (:8092) |

Registry: `ghcr.io/thalesgroup/t-keir` (see `deploy/versions.lock.yaml`).

```bash
make images              # all targets, native platform
make image-api           # one target
make image-hmi
make images-push         # multi-arch + push
make images-sign         # cosign keyless
```

Base images are digest-pinned. `MODEL_MODE=fetch|baked` applies to `tkeir-api`.
