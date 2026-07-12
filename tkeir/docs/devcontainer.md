# Dev Container

The repository ships a VS Code / Cursor **Dev Container** for a reproducible T-KEIR
development environment with Python 3.11, `uv`, Tesseract OCR, and Docker socket access
(required for Vespa).

Configuration lives in `.devcontainer/` (`devcontainer.json`, `docker-compose.yml`,
`Dockerfile.devcontainer`). The workspace is mounted at **`/workspace`** inside the
container.

## Prerequisites (host machine)

- [Docker Desktop](https://docs.docker.com/get-docker/) or Docker Engine + Compose v2 — **running before you open the container**
- [VS Code](https://code.visualstudio.com/) or [Cursor](https://cursor.com/)
- **Dev Containers** extension:
  - VS Code: [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
  - Cursor: install **Dev Containers** from the Extensions panel (same extension ID as VS Code)

Run the host preflight check manually if needed:

```bash
bash .devcontainer/preflight-host.sh
```

## Enter from the terminal (script)

No IDE required — from the repository root on the **host**:

```bash
bash .devcontainer/enter-devcontainer.sh
# or
make devcontainer
```

Starts the container if needed, runs first-time setup, then opens `bash` in `/workspace`.
Run a single command:

```bash
bash .devcontainer/enter-devcontainer.sh -- make setup
bash .devcontainer/enter-devcontainer.sh -- make ci
```

Options: `--build` (rebuild image), `--rebuild` (destroy and recreate). Install the
[devcontainer CLI](https://github.com/devcontainers/cli) for the full lifecycle
(`npm install -g @devcontainers/cli`); otherwise the script falls back to `docker compose`.

## How to enter the dev container (Cursor or VS Code)

1. **File → Open Folder…** and select the cloned `t-keir` directory.
2. Ensure Docker Desktop is running.
3. **Command Palette** (`Cmd+Shift+P` on macOS, `Ctrl+Shift+P` on Linux/Windows).
4. Choose **`Dev Containers: Reopen in Container`**.
   - First time or after Dockerfile changes: use **`Dev Containers: Rebuild and Reopen in Container`** instead.
5. Wait until the status bar shows **Dev Container: T-Keir Dev Environment** and the
   terminal prompt is inside `/workspace`.
6. On first create, `post-create.sh` runs `make install` automatically. When it finishes,
   run `make setup` for spaCy models and a full environment check.

### VS Code

Same steps as Cursor: open the repo root → Command Palette →
**`Dev Containers: Reopen in Container`**.

### Verify you are inside the container

| Check | Expected |
|---|---|
| Status bar (bottom-left) | `Dev Container: T-Keir Dev Environment` |
| Terminal `pwd` | `/workspace` |
| Python | `tkeir/.venv/bin/python` (3.11) |
| Docker | `docker ps` works (host socket mounted) |

```bash
pwd
python --version
which tkeir-pipeline   # shell alias → uv run from tkeir/
```

### Open a second terminal

Use **Terminal → New Terminal** in Cursor/VS Code. All terminals run inside the
dev container once the window has reopened in the container.

### Leave the dev container

**Command Palette** → **`Dev Containers: Reopen Folder Locally`**.

This closes the remote session and returns to editing files on the host filesystem.

## Rebuild and stop (from the host)

Run these in a **host** terminal (not inside the container), from the repository root:

```bash
bash .devcontainer/rebuild-devcontainer.sh
```

```bash
bash .devcontainer/stop-devcontainer.sh
```

Rebuild from the editor: **Command Palette** → **`Dev Containers: Rebuild Container`**.

## What is installed

| Component | Location / notes |
|---|---|
| Python | 3.11 via devcontainer feature |
| Node.js / npm | 22 via devcontainer feature (for `tkeir-hmi/`) |
| `uv` | Package manager for `tkeir/` |
| Tesseract | `eng` + `fra` (PDF OCR in pipeline) |
| Docker CLI | Host socket mounted for Vespa containers |
| Workspace | Repository mounted at `/workspace` |
| Virtualenv | `/workspace/tkeir/.venv` |

Shell aliases in the container image:

```bash
tkeir-pipeline   # runs uv run tkeir-pipeline from tkeir/
```

## Forwarded ports

| Port | Service |
|---|---|
| 8000 | MkDocs (`make docs`) |
| 8080 | Vespa search API |
| 8090 | FastAPI RAG API |
| 19071 | Vespa config server |
| 3000 | tkeir-hmi (`cd tkeir-hmi && npm install && npm run dev`) |

## Typical workflow inside the container

```bash
# 1. Full setup (deps, spaCy models, tokenizer pickle, Tesseract check)
make setup

# 2. Run pipeline on fixtures
make quickstart

# 3. Start Vespa + index test fixtures + RAG API
cd vespa
make bootstrap
make index-fixtures   # if tests/indexing/output is empty
make index
make rag

# 4. Sample RAG query (separate terminal)
make rag-query RAG_QUERY="Who is Rob Brown?"

# 5. Quality gates
make ci
```

Indexing fixtures live under `tkeir/tests/indexing/` (portable `tests/indexing/input`
PDFs and `tests/indexing/output` pipeline JSON).

## Environment variables

| Variable | Default in devcontainer | Purpose |
|---|---|---|
| `TRANSFORMERS_CACHE` | `/workspace/.cache/models` | Hugging Face / model cache |
| `PROVIDER` | `ollama` | LLM/embeddings provider for indexing and RAG |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama on the **host** (not container `localhost`) |
| `VESPA_URL` | `http://host.docker.internal:8080` | Vespa document/search API (ports published by Docker on host) |
| `VESPA_CONFIG_URL` | `http://host.docker.internal:19071` | Vespa config server |

Ollama must run on the **host** when using `PROVIDER=ollama`:

```bash
ollama serve
ollama pull bge-m3
ollama pull mistral-nemo
```

Inside the devcontainer, `localhost:11434` points at the container itself — use
`host.docker.internal` (set automatically in `.devcontainer/docker-compose.yml`).
After changing compose env, **rebuild the devcontainer** or export the variables manually.

## Troubleshooting

**Vespa bootstrap timeout** — ensure Docker is running on the host and port 8080 is free.

**Ollama connection errors (`httpx.ConnectError` on `make index`)** — Ollama runs on the
host, not inside the devcontainer. Start it on the host (`ollama serve`) and pull
`bge-m3`. Ensure `OLLAMA_BASE_URL=http://host.docker.internal:11434` (default after
devcontainer rebuild). Test from inside the container:

```bash
curl -s "$OLLAMA_BASE_URL/api/tags" | head
```

**Permission errors on Docker socket** — add your host user to the `docker` group or run
Docker Desktop.

**Re-sync Python deps after pull**:

```bash
bash .devcontainer/ensure-venv.sh   # inside container, if host .venv conflicts
make install
```

**`uv sync` fails on `.venv/lib` (Directory not empty)** — the workspace bind-mount
contains a virtualenv built on the host. Inside the container run
`bash .devcontainer/ensure-venv.sh` then `make install`, or from the host remove
`tkeir/.venv` and rerun `make devcontainer`.
