# Container images

| Target | Dockerfile | Base | Entrypoint |
|--------|------------|------|------------|
| `tkeir-lib` | `Dockerfile.tkeir-lib` | `PYTHON_BASE` | *(shared venv — not run alone)* |
| `tkeir-api` | `Dockerfile.tkeir-api` | **tkeir-lib** | `tkeir-rag` (:8090) |
| `tkeir-ingest` | `Dockerfile.tkeir-ingest` | **tkeir-lib** | `tkeir-ingest` (:8091) |
| `tkeir-mcp` | `Dockerfile.tkeir-mcp` | **tkeir-lib** | `tkeir-mcp` (:8093) |
| `tkeir-agent` | `Dockerfile.tkeir-agent` | **tkeir-lib** | `tkeir-agent` (:8092) |
| `tkeir-governor` | `Dockerfile.tkeir-governor` | **tkeir-lib** | `tkeir-governor` (:8094) |
| `tkeir-audit` | `Dockerfile.tkeir-audit` | **tkeir-lib** | `tkeir-audit` (:8093) |
| `tkeir-indexer` | `Dockerfile.tkeir-indexer` | `PYTHON_BASE` | `entrypoint-indexer.sh` (OCR) |
| `tkeir-indexer-slim` | same, `INSTALL_OCR=0` | `PYTHON_BASE` | same without Tesseract |
| `tkeir-hmi` | `Dockerfile.tkeir-hmi` | `NODE_BASE` | Next.js standalone (:3000) |

`tkeir-lib` runs `uv sync` **once** (including `--group audit` and
`--group models` so `tkeir-ingest` can run the spaCy pipeline). Python service
images are thin layers (`FROM tkeir-lib`) so the base is not rebuilt per
container. HMI is Node-only; indexer keeps a separate tree (also `models` +
optional OCR).

Registry (local default): `local` — see `deploy/versions.lock.yaml`.
Publish: `make images-push IMAGE_REGISTRY=ghcr.io/thalesgroup/t-keir`.

```bash
make images              # all targets (lib first), native platform
make image-lib           # shared Python base only
make image-api           # also builds tkeir-lib via bake context
make image-hmi
make images-push         # multi-arch + push
make images-sign         # cosign keyless
```

Base images are digest-pinned. `MODEL_MODE=fetch|baked` applies to `tkeir-api`.

Compose build of api/ingest/… expects `local/tkeir-lib:$IMAGE_TAG` already
present (`make images` or `make image-lib` first).

## Disk / BuildKit I/O errors

`Input/output error` while installing large wheels (e.g. sympy) or on
`COPY --from=builder …/.venv` usually means the **host or Docker Desktop disk
is full / corrupted**, not a bad Dockerfile. Check free space (`df -h`); Docker
Desktop alone can consume hundreds of GiB under
`~/Library/Containers/com.docker.docker`.

Recover locally:

```bash
# Free Docker build cache + unused images (destructive to unused local images)
docker builder prune -af
docker system prune -af --volumes

# If the daemon still reports blob I/O errors: Docker Desktop → Troubleshoot
# → Clean / Purge data, then retry:
make images
```

Builder stages also strip `tests` / `__pycache__` from the venv after `uv sync`
to shrink the runtime COPY.
