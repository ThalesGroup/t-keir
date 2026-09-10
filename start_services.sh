#!/usr/bin/env bash
# Title: start_services.sh — tmux orchestrator for hybrid demo Makefile targets.
#
# Starts Vespa (vespa-up + bootstrap) → Keycloak → SPIRE → SearXNG → collector →
# ingest → RAG → governor → audit → OKF → agent → HMI in dedicated tmux windows
# with health gates. Docker windows (Vespa / Keycloak / SPIRE / SearXNG) follow
# \`docker logs -f\` after start instead of dropping to a shell.
#
# Usage:
#   ./start_services.sh              # create session and attach (USECASE=osint)
#   USECASE=enterprise ./start_services.sh
#   TKEIR_USECASE=my_pack ./start_services.sh
#   ./start_services.sh --usecase enterprise
#   ./start_services.sh --no-attach  # create only (CI / nested tmux)
#   ./start_services.sh --skip-check-install
#   SESSION=tkeir-demo ./start_services.sh
#   TMUX_BIN=/opt/homebrew/bin/tmux ./start_services.sh
#
# Usecase pack (datasets/<name>/): --usecase, USECASE, or TKEIR_USECASE.
# Default osint. Exported into every tmux pane so Keycloak, ingest, RAG,
# agent, and HMI stay on the same pack (see docs/tools/usecase.md).
#
# Shortcuts (no prefix):
#   TAB     next window
#   CTRL+R  restart active pane (respawn-pane -k)
#   ESC     make down + kill session
#
# If any service fails its health check, the script runs make down and exits.
# Preserve runtime DBs on ESC shutdown:
#   KEEP_DATA=1 ./start_services.sh
#
# Dev install gate (make check-install) runs first unless skipped:
#   SKIP_CHECK_INSTALL=1 ./start_services.sh
#   STRICT=1 ./start_services.sh          # warnings fail check-install
# Author: T-KEIR
# Copyright (c) 2026 Thales — MIT License

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSION="${SESSION:-tkeir-demo}"
ATTACH="${ATTACH:-1}"
HEALTH_POLL_SECONDS="${HEALTH_POLL_SECONDS:-2}"
KEEP_DATA="${KEEP_DATA:-0}"
SKIP_CHECK_INSTALL="${SKIP_CHECK_INSTALL:-0}"
USECASE_CLI=""
TMUX_CMD=""

# Per-service readiness timeouts (seconds).
TIMEOUT_VESPA="${TIMEOUT_VESPA:-180}"
TIMEOUT_KEYCLOAK="${TIMEOUT_KEYCLOAK:-180}"
TIMEOUT_SPIRE="${TIMEOUT_SPIRE:-180}"
TIMEOUT_SEARXNG="${TIMEOUT_SEARXNG:-90}"
TIMEOUT_COLLECTOR="${TIMEOUT_COLLECTOR:-180}"
TIMEOUT_INGEST="${TIMEOUT_INGEST:-180}"
TIMEOUT_RAG="${TIMEOUT_RAG:-180}"
TIMEOUT_GOVERNOR="${TIMEOUT_GOVERNOR:-180}"
TIMEOUT_AUDIT="${TIMEOUT_AUDIT:-120}"
TIMEOUT_OKF="${TIMEOUT_OKF:-120}"
TIMEOUT_AGENT="${TIMEOUT_AGENT:-180}"
TIMEOUT_HMI="${TIMEOUT_HMI:-180}"

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

require_bin() {
  local bin="$1"
  command -v "$bin" >/dev/null 2>&1 || die "'$bin' is not installed or not on PATH"
}

# Resolve tmux binary. On macOS prefer Homebrew installs
# (/opt/homebrew/bin/tmux on Apple Silicon, /usr/local/bin/tmux on Intel).
resolve_tmux() {
  local candidate
  if [[ -n "${TMUX_BIN:-}" ]]; then
    [[ -x "$TMUX_BIN" ]] || die "TMUX_BIN is set but not executable: $TMUX_BIN"
    printf '%s\n' "$TMUX_BIN"
    return 0
  fi

  if [[ "$(uname -s)" == "Darwin" ]]; then
    for candidate in /opt/homebrew/bin/tmux /usr/local/bin/tmux; do
      if [[ -x "$candidate" ]]; then
        printf '%s\n' "$candidate"
        return 0
      fi
    done
    if command -v brew >/dev/null 2>&1; then
      candidate="$(brew --prefix 2>/dev/null)/bin/tmux"
      if [[ -x "$candidate" ]]; then
        printf '%s\n' "$candidate"
        return 0
      fi
    fi
    die "tmux not found on this macOS Homebrew system.
Install with:  brew install tmux
Expected path: /opt/homebrew/bin/tmux  (Apple Silicon)
               /usr/local/bin/tmux     (Intel)
Or set TMUX_BIN=/path/to/tmux"
  fi

  candidate="$(command -v tmux 2>/dev/null || true)"
  [[ -n "$candidate" && -x "$candidate" ]] || die "'tmux' is not installed or not on PATH"
  printf '%s\n' "$candidate"
}

log() {
  printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

# Resolve datasets/<name>/ pack. CLI --usecase wins, then USECASE / TKEIR_*.
resolve_usecase() {
  local raw
  raw="${USECASE_CLI:-${USECASE:-${TKEIR_USECASE:-${TKEIR_AGENT_USECASE:-${TKEIR_DATASET:-${TKEIR_BUSINESS_ONTOLOGY_DATASET:-osint}}}}}}"
  raw="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
  [[ -n "$raw" ]] || raw="osint"
  USECASE="$raw"
  TKEIR_USECASE="$raw"
  TKEIR_AGENT_USECASE="$raw"
  TKEIR_BUSINESS_ONTOLOGY_DATASET="$raw"
  export USECASE TKEIR_USECASE TKEIR_AGENT_USECASE TKEIR_BUSINESS_ONTOLOGY_DATASET
  export NEXT_PUBLIC_TKEIR_USECASE="$raw"
}

validate_usecase_pack() {
  local pack="$ROOT/datasets/$USECASE"
  [[ -d "$pack" ]] || die "usecase pack not found: ${pack}
Set USECASE / TKEIR_USECASE to a folder under datasets/ (default osint).
See docs/tools/usecase.md"
  [[ -f "$pack/agent_orchestrator.yaml" ]] || die "missing ${pack}/agent_orchestrator.yaml
Every usecase pack needs agent_orchestrator.yaml (see docs/tools/usecase.md)"
  [[ -f "$pack/keycloak.json" ]] || die "missing ${pack}/keycloak.json
Keycloak sync loads datasets/<usecase>/keycloak.json (see docs/tools/usecase.md)"
  if [[ ! -f "$pack/hmi.json" ]]; then
    log "warn: ${pack}/hmi.json missing — HMI will fall back to OSINT presets"
  fi
}

# Exports baked into tmux panes so bash -lc / CTRL+R keep the selected pack.
usecase_export_block() {
  cat <<EOF
export USECASE=$(printf '%q' "$USECASE")
export TKEIR_USECASE=$(printf '%q' "$TKEIR_USECASE")
export TKEIR_AGENT_USECASE=$(printf '%q' "$TKEIR_AGENT_USECASE")
export TKEIR_BUSINESS_ONTOLOGY_DATASET=$(printf '%q' "$TKEIR_BUSINESS_ONTOLOGY_DATASET")
export NEXT_PUBLIC_TKEIR_USECASE=$(printf '%q' "$TKEIR_USECASE")
EOF
}

# Prefix for make in this process (keycloak-sync, and any host-side make).
make_with_usecase() {
  USECASE="$USECASE" \
    TKEIR_USECASE="$TKEIR_USECASE" \
    TKEIR_AGENT_USECASE="$TKEIR_AGENT_USECASE" \
    TKEIR_BUSINESS_ONTOLOGY_DATASET="$TKEIR_BUSINESS_ONTOLOGY_DATASET" \
    make "$@"
}

# Tear down the whole demo stack when a service fails to become ready.
abort_stack() {
  local reason="$*"
  log "ABORT: ${reason}"
  log "stopping all services via make down…"
  (
    cd "$ROOT" \
      && KEEP_DATA="${KEEP_DATA:-0}" make down
  ) || log "make down returned non-zero (continuing cleanup)"
  if [[ -n "${TMUX_CMD:-}" ]] && "$TMUX_CMD" has-session -t "$SESSION" 2>/dev/null; then
    log "killing tmux session '${SESSION}'"
    "$TMUX_CMD" kill-session -t "$SESSION" || true
  fi
  die "${reason} — stack stopped with make down"
}

# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

wait_http() {
  local name="$1"
  local url="$2"
  local timeout="${3:-120}"
  local start now
  start="$(date +%s)"
  log "waiting for ${name}: ${url} (timeout ${timeout}s)"
  while true; do
    if curl -fsS -o /dev/null --connect-timeout 2 --max-time 5 "$url" 2>/dev/null; then
      log "ready: ${name}"
      return 0
    fi
    now="$(date +%s)"
    if (( now - start >= timeout )); then
      abort_stack "${name} not ready after ${timeout}s (${url})"
    fi
    sleep "$HEALTH_POLL_SECONDS"
  done
}

wait_docker_healthy() {
  local name="$1"
  local container="$2"
  local timeout="${3:-180}"
  local require_healthy="${4:-0}"
  local start now st
  start="$(date +%s)"
  log "waiting for ${name} container '${container}' (timeout ${timeout}s)"
  while true; do
    st="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || echo missing)"
    if [[ "$st" == "healthy" ]]; then
      log "ready: ${name} (${container}=healthy)"
      return 0
    fi
    if [[ "$require_healthy" != "1" && "$st" == "running" ]]; then
      log "ready: ${name} (${container}=running)"
      return 0
    fi
    now="$(date +%s)"
    if (( now - start >= timeout )); then
      abort_stack "${name} not ready after ${timeout}s (container=${container} status=${st})"
    fi
    sleep "$HEALTH_POLL_SECONDS"
  done
}

# SPIRE: server must be healthy; agent should be running (or healthy).
wait_spire() {
  local timeout="${1:-180}"
  wait_docker_healthy "SPIRE server" "tkeir-spire-server" "$timeout" 1
  wait_docker_healthy "SPIRE agent" "tkeir-spire-agent" "$timeout" 0
}

# ---------------------------------------------------------------------------
# tmux helpers
# ---------------------------------------------------------------------------

configure_session() {
  # Keep pane output after process exit / crash.
  "$TMUX_CMD" set-option -t "$SESSION" -g remain-on-exit on
  "$TMUX_CMD" set-option -t "$SESSION" -g mouse on
  "$TMUX_CMD" set-option -t "$SESSION" -g history-limit 10000
  "$TMUX_CMD" set-option -t "$SESSION" -g status on
  "$TMUX_CMD" set-option -t "$SESSION" -g status-interval 5
  "$TMUX_CMD" set-option -t "$SESSION" -g status-justify left
  "$TMUX_CMD" set-option -t "$SESSION" -g status-left-length 56
  "$TMUX_CMD" set-option -t "$SESSION" -g status-right-length 140
  "$TMUX_CMD" set-option -t "$SESSION" -g status-style "bg=colour235,fg=colour250"
  "$TMUX_CMD" set-option -t "$SESSION" -g window-status-current-style "bg=colour238,fg=colour220,bold"
  "$TMUX_CMD" set-option -t "$SESSION" -g status-left "#[bold] ${SESSION} #[fg=colour117]${USECASE} "
  "$TMUX_CMD" set-environment -t "$SESSION" USECASE "$USECASE"
  "$TMUX_CMD" set-environment -t "$SESSION" TKEIR_USECASE "$TKEIR_USECASE"
  "$TMUX_CMD" set-environment -t "$SESSION" TKEIR_AGENT_USECASE "$TKEIR_AGENT_USECASE"
  "$TMUX_CMD" set-environment -t "$SESSION" TKEIR_BUSINESS_ONTOLOGY_DATASET "$TKEIR_BUSINESS_ONTOLOGY_DATASET"
  "$TMUX_CMD" set-environment -t "$SESSION" NEXT_PUBLIC_TKEIR_USECASE "$TKEIR_USECASE"
  "$TMUX_CMD" set-option -t "$SESSION" -g status-right "#[fg=colour117][ TAB: Next Service ]#[fg=colour245] | #[fg=colour214][ CTRL+R: Restart Active Service ]#[fg=colour245] | #[fg=colour203][ ESC: Global Shutdown (make down) ] "

  # No-prefix shortcuts (session-scoped where supported; -n = root table).
  "$TMUX_CMD" bind-key -n Tab next-window
  "$TMUX_CMD" bind-key -n C-r respawn-pane -k
  # ESC → wipe-or-keep via KEEP_DATA, then kill this session.
  "$TMUX_CMD" bind-key -n Escape run-shell "cd $(printf '%q' "$ROOT") && KEEP_DATA=$(printf '%q' "$KEEP_DATA") make down; $(printf '%q' "$TMUX_CMD") kill-session -t $(printf '%q' "$SESSION") || true"
}

# Create (or append) a window whose pane command is the make target.
# Using an initial pane command (not send-keys) makes CTRL+R / respawn-pane -k
# re-run the same service command.
WINDOW_INDEX=-1

_start_pane() {
  local title="$1"
  local pane_script="$2"
  WINDOW_INDEX=$((WINDOW_INDEX + 1))

  if (( WINDOW_INDEX == 0 )); then
    "$TMUX_CMD" new-session -d -s "$SESSION" -c "$ROOT" -n "$title" \
      bash -lc "$pane_script"
    configure_session
  else
    "$TMUX_CMD" new-window -t "$SESSION" -c "$ROOT" -n "$title" \
      bash -lc "$pane_script"
  fi
}

start_window() {
  local title="$1"
  local cmd="$2"
  local pane_script
  # shellcheck disable=SC2016
  pane_script="$(cat <<EOF
cd $(printf '%q' "$ROOT") || exit 1
$(usecase_export_block)
printf '\\n==> %s\\n\\n' $(printf '%q' "$cmd")
${cmd}
status=\$?
printf '\\n[%s] exited %s — CTRL+R to restart, ESC for make down\\n' $(printf '%q' "$title") "\$status"
# Keep an interactive shell so remain-on-exit is not the only way to inspect logs.
exec bash
EOF
)"
  _start_pane "$title" "$pane_script"
  log "started window ${WINDOW_INDEX} ${title}: ${cmd}"
}

# Docker infra windows: run the up target, then follow container logs (no bash).
# Extra args are container names for \`docker logs -f\`. CTRL+R re-runs up + follow.
start_docker_window() {
  local title="$1"
  local cmd="$2"
  shift 2
  local containers=("$@")
  local pane_script containers_q="" c
  [[ ${#containers[@]} -gt 0 ]] || die "start_docker_window: need at least one container name"

  for c in "${containers[@]}"; do
    containers_q+=" $(printf '%q' "$c")"
  done

  # shellcheck disable=SC2016
  pane_script="$(cat <<EOF
cd $(printf '%q' "$ROOT") || exit 1
$(usecase_export_block)
printf '\\n==> %s\\n\\n' $(printf '%q' "$cmd")
${cmd}
status=\$?
if [[ \$status -ne 0 ]]; then
  printf '\\n[%s] start failed (exit %s) — CTRL+R to retry, ESC for make down\\n' \\
    $(printf '%q' "$title") "\$status"
  exec bash
fi

follow_logs() {
  local containers=($containers_q)
  local c pids=()
  printf '\\n==> docker logs -f --tail=100 %s\\n\\n' "\${containers[*]}"
  cleanup() {
    local p
    for p in "\${pids[@]:-}"; do
      kill "\$p" 2>/dev/null || true
    done
  }
  trap cleanup EXIT INT TERM
  if [[ \${#containers[@]} -eq 1 ]]; then
    docker logs -f --tail=100 "\${containers[0]}"
    return \$?
  fi
  for c in "\${containers[@]}"; do
    (
      docker logs -f --tail=100 "\$c" 2>&1 | while IFS= read -r line || [[ -n "\$line" ]]; do
        printf '[%s] %s\\n' "\$c" "\$line"
      done
    ) &
    pids+=(\$!)
  done
  wait
}

follow_logs
status=\$?
printf '\\n[%s] docker logs exited %s — CTRL+R to restart, ESC for make down\\n' \\
  $(printf '%q' "$title") "\$status"
exec bash
EOF
)"
  _start_pane "$title" "$pane_script"
  log "started window ${WINDOW_INDEX} ${title}: ${cmd} → docker logs -f ${containers[*]}"
}

# ---------------------------------------------------------------------------
# Main sequence
# ---------------------------------------------------------------------------

main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --no-attach) ATTACH=0 ;;
      --attach) ATTACH=1 ;;
      --skip-check-install) SKIP_CHECK_INSTALL=1 ;;
      --usecase)
        [[ $# -ge 2 ]] || die "--usecase requires a pack name (osint, enterprise, …)"
        USECASE_CLI="$2"
        shift
        ;;
      --usecase=*)
        USECASE_CLI="${1#--usecase=}"
        [[ -n "$USECASE_CLI" ]] || die "--usecase requires a pack name"
        ;;
      -h|--help)
        sed -n '1,45p' "$0"
        exit 0
        ;;
      *) die "unknown argument: $1" ;;
    esac
    shift
  done

  require_bin make
  require_bin curl
  require_bin docker

  TMUX_CMD="$(resolve_tmux)"
  log "using tmux: $TMUX_CMD"

  [[ -f "$ROOT/Makefile" ]] || die "Makefile not found in $ROOT"

  cd "$ROOT"

  resolve_usecase
  validate_usecase_pack
  log "usecase=$USECASE (datasets/${USECASE}/)"

  if [[ "$SKIP_CHECK_INSTALL" == "1" ]]; then
    log "skipping make check-install (SKIP_CHECK_INSTALL=1)"
  else
    log "verifying local/dev install via make check-install"
    if ! make check-install \
      STRICT="${STRICT:-0}" \
      SKIP_DOCKER="${SKIP_DOCKER:-0}" \
      SKIP_HMI="${SKIP_HMI:-0}" \
      SKIP_SPACY="${SKIP_SPACY:-0}"; then
      die "make check-install failed — fix FAIL items (see make check-install) or re-run with --skip-check-install"
    fi
    log "check-install OK"
  fi

  if "$TMUX_CMD" has-session -t "$SESSION" 2>/dev/null; then
    log "session '$SESSION' already exists — killing it for a clean start"
    "$TMUX_CMD" kill-session -t "$SESSION" || true
  fi

  log "orchestrating hybrid demo into tmux session '$SESSION'"
  log "root=$ROOT KEEP_DATA=$KEEP_DATA USECASE=$USECASE"

  # Container first (no image pull), then deploy schemas so :8080 serves the app.
  # Docker panes follow container logs (CTRL+R re-runs up + logs).
  start_docker_window "[VESPA]" "make vespa-up && make bootstrap" vespa
  wait_http "Vespa config" "http://127.0.0.1:19071/state/v1/health" "$TIMEOUT_VESPA"
  wait_http "Vespa query" "http://127.0.0.1:8080/state/v1/health" "$TIMEOUT_VESPA"
  wait_http "Vespa application" "http://127.0.0.1:19071/application/v2/tenant/default/application/default" "$TIMEOUT_VESPA"

  start_docker_window "[KEYCLOAK]" "make keycloak-up USECASE=${USECASE}" tkeir-keycloak tkeir-keycloak-db
  wait_http "Keycloak" "http://127.0.0.1:8082/realms/tkeir" "$TIMEOUT_KEYCLOAK"
  # Re-sync personas/roles/clearance after Keycloak is healthy (idempotent).
  log "registering Keycloak personas for USECASE=${USECASE} (make keycloak-sync-demo-users)…"
  if ! make_with_usecase keycloak-sync-demo-users; then
    abort_stack "Keycloak persona sync failed (USECASE=${USECASE})"
  fi
  log "Keycloak personas registered (USECASE=${USECASE})"

  start_docker_window "[SPIRE]" "make spire-up" tkeir-spire-server tkeir-spire-agent
  wait_spire "$TIMEOUT_SPIRE"

  start_docker_window "[SEARXNG]" "make searxng-up" searxng
  wait_http "SearXNG" "http://127.0.0.1:8888/healthz" "$TIMEOUT_SEARXNG"

  start_window "[COLLECTOR]" "make collector-up"
  wait_http "Collector" "http://127.0.0.1:8096/health" "$TIMEOUT_COLLECTOR"

  # index-up = schema init + long-running ingest (:8091)
  start_window "[INDEX]" "make index-up USECASE=${USECASE}"
  wait_http "Ingest" "http://127.0.0.1:8091/health" "$TIMEOUT_INGEST"

  start_window "[RAG]" "make rag-up USECASE=${USECASE}"
  wait_http "RAG" "http://127.0.0.1:8090/health" "$TIMEOUT_RAG"

  start_window "[GOVERNOR]" "make governor-up"
  wait_http "Governor" "http://127.0.0.1:8094/health" "$TIMEOUT_GOVERNOR"

  start_window "[AUDIT]" "make audit-up"
  wait_http "Audit" "http://127.0.0.1:8093/health" "$TIMEOUT_AUDIT"

  start_window "[OKF]" "make okf-up"
  wait_http "OKF" "http://127.0.0.1:8095/health" "$TIMEOUT_OKF"

  # make agent also ensures SPIRE (idempotent if already up)
  start_window "[AGENT]" "make agent USECASE=${USECASE}"
  wait_http "Agent" "http://127.0.0.1:8092/health" "$TIMEOUT_AGENT"

  start_window "[HMI]" "make hmi-up USECASE=${USECASE}"
  wait_http "HMI" "http://127.0.0.1:3000" "$TIMEOUT_HMI"

  log "all services reported ready"
  log "usecase=$USECASE  HMI: http://127.0.0.1:3000"
  log "shortcuts: TAB=next | CTRL+R=restart pane | ESC=make down + exit"

  if [[ "$ATTACH" == "1" ]]; then
    # Select first window and attach (or switch-client if already inside tmux).
    # Env TMUX / TMUX_PANE are set by a parent tmux client — do not confuse with TMUX_CMD.
    "$TMUX_CMD" select-window -t "${SESSION}:0"
    if [[ -n "${TMUX:-}" ]]; then
      "$TMUX_CMD" switch-client -t "$SESSION"
    else
      exec "$TMUX_CMD" attach-session -t "$SESSION"
    fi
  else
    log "session ready (not attaching): $TMUX_CMD attach -t $SESSION"
  fi
}

main "$@"
