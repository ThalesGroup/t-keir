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
| `[KEYCLOAK]` | `make keycloak-up` + pack sync | `docker logs -f` keycloak (+ db) | realm + `datasets/<USECASE>/keycloak.json` personas |
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

`make setup` installs HMI Node deps (`make hmi-install` → `npm ci`, including
Cytoscape.js). `make hmi-up` re-runs that install if `node_modules/cytoscape`
is missing, copies `.env.local.example` → `.env.local` when missing, then runs
`npm run dev` on port **3000**. It also copies `datasets/<USECASE>/hmi.json` to
`tkeir-hmi/public/usecase.json` and sets `NEXT_PUBLIC_TKEIR_USECASE`.

## Usecase pack

The launcher selects `datasets/<name>/` the same way as Make:

| Source | Example |
|--------|---------|
| env `USECASE` | `USECASE=enterprise ./start_services.sh` |
| env `TKEIR_USECASE` | `TKEIR_USECASE=enterprise ./start_services.sh` |
| flag `--usecase` | `./start_services.sh --usecase enterprise` |

Default is **osint**. The resolved name is exported as `USECASE`,
`TKEIR_USECASE`, `TKEIR_AGENT_USECASE`, `TKEIR_BUSINESS_ONTOLOGY_DATASET`, and
`NEXT_PUBLIC_TKEIR_USECASE` into every tmux pane (so `CTRL+R` keeps the pack).
The pack must contain `agent_orchestrator.yaml` and `keycloak.json`. New pack
from the OSINT tree: [Create a usecase pack](../tools/usecase.md).

Shipped packs: **osint** (`analyst` / `c2-admin`, …) and **enterprise**
(`ceo` / `enterprise-admin`, …).

## Prerequisites

- Same host tools as [Zero to Hero §2](../zero_to_hero.md#2-prerequisites)
- `tmux` installed (`brew install tmux` on macOS)
- Vespa image already local (`make pull-vespa`, also run by `make setup` when
  the image is missing) — `vespa-up` does **not** pull
- Docker daemon running (Vespa / Keycloak / SPIRE)

Quick gate:

```bash
make check-install
```

## Usage

```bash
# From the repo root — creates session tkeir-demo and attaches (USECASE=osint)
./start_services.sh

# Enterprise (or any datasets/<name>/ pack) — same launcher
USECASE=enterprise ./start_services.sh
# equivalent: TKEIR_USECASE=enterprise ./start_services.sh
# equivalent: ./start_services.sh --usecase enterprise

# Create windows but do not attach (nested tmux / CI)
./start_services.sh --no-attach

# Skip the install verification gate
./start_services.sh --skip-check-install

# Keep runtime DBs when tearing down (ESC or abort)
KEEP_DATA=1 ./start_services.sh

# Persist the Vespa index across `make down` (tar of the data volume).
# Restore runs when the live volume is empty; save runs on ESC / abort.
INDEX_SNAPSHOT=1 ./start_services.sh
# or an explicit archive:
# INDEX_SNAPSHOT=/path/to/osint.tar.gz ./start_services.sh
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
| `ESC` | Global shutdown: save Vespa index if `INDEX_SNAPSHOT` is set, then `make down` + kill the tmux session |

`remain-on-exit` is on, so pane logs stay visible if a process exits.

## Failure behaviour

If **any** service fails its health check (timeout), the script:

1. Logs the failing service / URL  
2. Runs **`make down`** (stops containers, host listeners, and by default wipes
   runtime state — use `KEEP_DATA=1` to preserve DBs). When `INDEX_SNAPSHOT` is
   set, the Vespa volume is tarred first; a failed save forces `KEEP_DATA=1`
   so the live index is not wiped unsaved.  
3. Kills the tmux session and exits non-zero  

So a half-started stack is not left behind after an abort.

## Vespa index snapshot

Re-indexing a full corpus is slow (embeddings). Set **`INDEX_SNAPSHOT`** so the
launcher tars the Vespa data volume on shutdown and restores it on the next
start when the live volume is empty:

| Value | Archive |
|-------|---------|
| `1` / `true` / `yes` / `on` | `.vespa-snapshots/<USECASE>/index.tar.gz` |
| path to a `.tar.gz` (or a directory) | that file (directory → `index.tar.gz` inside) |
| unset / `0` / `false` / `no` / `off` | disabled |

```bash
INDEX_SNAPSHOT=1 ./start_services.sh
# ingest once, then ESC — next start restores the index without re-ingest

# Force a replace even if a live volume exists:
INDEX_SNAPSHOT=1 make restore-index && ./start_services.sh
```

Manual targets: `make save-index` / `make restore-index` (`INDEX_SNAPSHOT=1`
or a path; `USECASE=` selects the default archive name).

## Related

- Manual terminal-by-terminal order: [Zero to Hero §5.2.a](../zero_to_hero.md#52a-hybrid-demo-vespa--keycloak--spire-infra-host-services)
- Tear-down / wipe: `make down` / `KEEP_DATA=1 make down` — see Zero to Hero and
  [Compose](compose.md)
- Install verification: `make check-install`
- Vespa image pull (explicit): `make pull-vespa`
