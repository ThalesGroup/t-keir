# Hybrid demo launcher — `start_services.sh`

> Orchestrate the [§5.2.a hybrid demo](../zero_to_hero.md#52a-hybrid-demo-vespa--keycloak--spire-infra-host-services)
> in one **tmux** session: infrastructure containers plus host Python services,
> with health gates between steps.

The script lives at the **repository root** next to the `Makefile`:

```bash
./start_services.sh
```

(Some notes call it “run services”; the file name is **`start_services.sh`**.)

## What it starts

| Window | Command | Pane stays on | Ready when |
|--------|---------|---------------|------------|
| `[VESPA]` | `make vespa-up && make bootstrap` | `docker logs -f vespa` | config `:19071`, query `:8080`, app deployed |
| `[KEYCLOAK]` | `make keycloak-up` + demo sync | `docker logs -f` keycloak (+ db) | realm + demo personas (`analyst`, `humint`, …) |
| `[SPIRE]` | `make spire-up` | `docker logs -f` server + agent | SPIRE server healthy + agent running |
| `[SEARXNG]` | `make searxng-up` | `docker logs -f searxng` | SearXNG `:8888/healthz` |
| `[COLLECTOR]` | `make collector-up` | host process (bash on exit) | collector `:8096/health` |
| `[INDEX]` | `make index-up` | host process (bash on exit) | ingest `:8091/health` |
| `[RAG]` | `make rag-up` | host process (bash on exit) | RAG `:8090/health` |
| `[GOVERNOR]` | `make governor-up` | host process (bash on exit) | governor `:8094/health` |
| `[AUDIT]` | `make audit-up` | host process (bash on exit) | audit `:8093/health` |
| `[OKF]` | `make okf-up` | host process (bash on exit) | OKF `:8095/health` |
| `[AGENT]` | `make agent` | host process (bash on exit) | agent `:8092/health` |
| `[HMI]` | `make hmi-up` | host process (bash on exit) | UI `http://localhost:3000` |

Before creating the session it runs **`make check-install`** so the host
toolchain (uv, Docker, spaCy, Node, …) is verified. Skip with
`--skip-check-install` if you already know the environment is good.

On **macOS**, tmux is resolved from Homebrew first
(`/opt/homebrew/bin/tmux`, then `/usr/local/bin/tmux`). Override with
`TMUX_BIN=…`.

`make hmi-up` ensures `tkeir-hmi/node_modules` (via `make hmi-install` if
needed) and copies `.env.local.example` → `.env.local` when missing, then runs
`npm run dev` on port **3000**.

## Prerequisites

- Same host tools as [Zero to Hero §2](../zero_to_hero.md#2-prerequisites)
- `tmux` installed (`brew install tmux` on macOS)
- Vespa image already local (`make pull-vespa`) — `vespa-up` does **not** pull
- Docker daemon running (Vespa / Keycloak / SPIRE)

Quick gate:

```bash
make check-install
```

## Usage

```bash
# From the repo root — creates session tkeir-demo and attaches
./start_services.sh

# Create windows but do not attach (nested tmux / CI)
./start_services.sh --no-attach

# Skip the install verification gate
./start_services.sh --skip-check-install

# Keep runtime DBs when tearing down (ESC or abort)
KEEP_DATA=1 ./start_services.sh
```

Attach later:

```bash
tmux attach -t tkeir-demo
# or: /opt/homebrew/bin/tmux attach -t tkeir-demo
```

## Shortcuts (no tmux prefix)

Shown permanently in the status bar:

| Key | Action |
|-----|--------|
| `TAB` | Next service window |
| `CTRL+R` | Restart the active pane (`respawn-pane -k` → re-run that `make …`; Docker panes re-attach `docker logs -f`) |
| `ESC` | Global shutdown: `make down` + kill the tmux session |

`remain-on-exit` is on, so pane logs stay visible if a process exits.

## Failure behaviour

If **any** service fails its health check (timeout), the script:

1. Logs the failing service / URL  
2. Runs **`make down`** (stops containers, host listeners, and by default wipes
   runtime state — use `KEEP_DATA=1` to preserve DBs)  
3. Kills the tmux session and exits non-zero  

So a half-started stack is not left behind after an abort.

## Related

- Manual terminal-by-terminal order: [Zero to Hero §5.2.a](../zero_to_hero.md#52a-hybrid-demo-vespa--keycloak--spire-infra-host-services)
- Tear-down / wipe: `make down` / `KEEP_DATA=1 make down` — see Zero to Hero and
  [Compose](compose.md)
- Install verification: `make check-install`
- Vespa image pull (explicit): `make pull-vespa`
