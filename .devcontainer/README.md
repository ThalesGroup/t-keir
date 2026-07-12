# Dev Container — quick entry

Use this folder to develop T-KEIR inside Docker with Python 3.11, `uv`, Tesseract,
and access to the host Docker socket (for Vespa).

**Full guide:** [tkeir/docs/devcontainer.md](../tkeir/docs/devcontainer.md)

## Enter from the terminal (script)

From the repository root on your **host** machine:

```bash
bash .devcontainer/enter-devcontainer.sh
```

Or: `make devcontainer`

Run one command inside the container:

```bash
bash .devcontainer/enter-devcontainer.sh -- make setup
```

## Enter from Cursor or VS Code

1. Install [Docker Desktop](https://docs.docker.com/get-docker/) and start it.
2. Install the **Dev Containers** extension.
3. Open the repository root (`t-keir/`).
4. Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`) → **`Dev Containers: Reopen in Container`**.

## Other host scripts

```bash
bash .devcontainer/rebuild-devcontainer.sh   # destroy and recreate
bash .devcontainer/stop-devcontainer.sh      # stop compose stack
bash .devcontainer/preflight-host.sh         # check Docker before opening
```
