#!/usr/bin/env bash
# Title: check_install.sh — verify local/dev host install for T-KEIR.
#
# Used by: make check-install
# Exit 0 when all required checks pass (warnings allowed).
# Exit 1 when any required check fails.
#
# Env:
#   UV, PYTHON, ROOT, STRICT=1 (treat warnings as failures)
#   SKIP_DOCKER=1, SKIP_HMI=1, SKIP_SPACY=1
#
# Copyright (c) 2026 Thales — MIT License

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TKEIR_DIR="${TKEIR_DIR:-${ROOT}/tkeir}"
HMI_DIR="${HMI_DIR:-${ROOT}/tkeir-hmi}"
UV="${UV:-uv}"
PYTHON="${PYTHON:-3.11}"
STRICT="${STRICT:-0}"
SKIP_DOCKER="${SKIP_DOCKER:-0}"
SKIP_HMI="${SKIP_HMI:-0}"
SKIP_SPACY="${SKIP_SPACY:-0}"

OK=0
WARN=0
FAIL=0

green() { printf '\033[32m%s\033[0m' "$*"; }
yellow() { printf '\033[33m%s\033[0m' "$*"; }
red() { printf '\033[31m%s\033[0m' "$*"; }

pass() {
  OK=$((OK + 1))
  printf '  [%s] %s\n' "$(green OK)" "$*"
}

warn() {
  WARN=$((WARN + 1))
  printf '  [%s] %s\n' "$(yellow WARN)" "$*"
}

fail() {
  FAIL=$((FAIL + 1))
  printf '  [%s] %s\n' "$(red FAIL)" "$*"
}

have() { command -v "$1" >/dev/null 2>&1; }

# docker info can hang when the daemon is wedged — bound the wait.
_docker_daemon_reachable() {
  local pid i
  if have timeout; then
    timeout 8 docker info >/dev/null 2>&1
    return $?
  fi
  if have gtimeout; then
    gtimeout 8 docker info >/dev/null 2>&1
    return $?
  fi
  docker info >/dev/null 2>&1 &
  pid=$!
  i=0
  while kill -0 "$pid" 2>/dev/null && (( i < 16 )); do
    sleep 0.5
    i=$((i + 1))
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    return 1
  fi
  wait "$pid"
}

version_of() {
  local bin="$1"
  shift
  if have "$bin"; then
    "$bin" "$@" 2>/dev/null | head -n 1 | tr -d '\r'
  else
    echo "missing"
  fi
}

section() {
  printf '\n== %s ==\n' "$*"
}

# ---------------------------------------------------------------------------
# Host tools
# ---------------------------------------------------------------------------

section "Host tools"

if have git; then
  pass "git: $(version_of git --version)"
else
  fail "git not found"
fi

if have make; then
  pass "make: $(version_of make --version)"
else
  fail "make not found"
fi

if have curl; then
  pass "curl: $(version_of curl --version)"
else
  fail "curl not found (required for health checks / rag-query)"
fi

if have jq; then
  pass "jq: $(version_of jq --version)"
else
  fail "jq not found (required for rag-query / smoke-test / agent-run)"
fi

if have "$UV"; then
  pass "uv: $(version_of "$UV" --version)"
else
  fail "uv not found — https://docs.astral.sh/uv/getting-started/installation/"
fi

# Node / npm (HMI)
if [[ "$SKIP_HMI" == "1" ]]; then
  warn "HMI checks skipped (SKIP_HMI=1)"
else
  if have node; then
    node_ver="$(node -v 2>/dev/null | sed 's/^v//')"
    node_major="${node_ver%%.*}"
    if [[ "${node_major:-0}" -ge 20 ]]; then
      pass "node: v${node_ver}"
    else
      fail "node: v${node_ver} (need Node.js 20+ for tkeir-hmi)"
    fi
  else
    fail "node not found (need Node.js 20+ for tkeir-hmi)"
  fi
  if have npm; then
    pass "npm: $(version_of npm --version)"
  else
    fail "npm not found"
  fi
fi

# Docker
if [[ "$SKIP_DOCKER" == "1" ]]; then
  warn "Docker checks skipped (SKIP_DOCKER=1)"
else
  if have docker; then
    pass "docker: $(version_of docker --version)"
    if _docker_daemon_reachable; then
      pass "docker daemon reachable"
    else
      fail "docker daemon not reachable (start Docker Desktop / Colima / engine)"
    fi
    if docker compose version >/dev/null 2>&1; then
      pass "docker compose: $(docker compose version 2>/dev/null | head -n 1)"
    else
      fail "docker compose v2 not available (need: docker compose)"
    fi
  else
    fail "docker not found — https://docs.docker.com/get-docker/"
  fi
fi

# Tesseract (OCR — optional for many paths)
if have tesseract; then
  pass "tesseract: $(version_of tesseract --version)"
else
  warn "tesseract not found (OCR). Install: make install-tesseract"
fi

# tmux — used by start_services.sh (macOS Homebrew preferred)
tmux_bin=""
if [[ -n "${TMUX_BIN:-}" && -x "${TMUX_BIN}" ]]; then
  tmux_bin="$TMUX_BIN"
elif [[ "$(uname -s)" == "Darwin" ]]; then
  for candidate in /opt/homebrew/bin/tmux /usr/local/bin/tmux; do
    if [[ -x "$candidate" ]]; then
      tmux_bin="$candidate"
      break
    fi
  done
fi
if [[ -z "$tmux_bin" ]] && have tmux; then
  tmux_bin="$(command -v tmux)"
fi
if [[ -n "$tmux_bin" ]]; then
  pass "tmux: $tmux_bin ($( "$tmux_bin" -V 2>/dev/null || true))"
else
  warn "tmux not found (optional; needed for ./start_services.sh). macOS: brew install tmux"
fi

# SearXNG image (optional until collector / start_services)
if [[ "${SKIP_DOCKER:-0}" != "1" ]] && have docker; then
  if docker image inspect docker.io/searxng/searxng:latest >/dev/null 2>&1 \
    || docker image inspect searxng/searxng:latest >/dev/null 2>&1; then
    pass "searxng image: present"
  else
    warn "searxng image not pulled (optional). Run: make pull-searxng"
  fi
fi

# Ollama optional
if have ollama; then
  pass "ollama: present ($(version_of ollama --version))"
else
  warn "ollama not found (optional local LLM on macOS)"
fi

# ---------------------------------------------------------------------------
# Python / tkeir package
# ---------------------------------------------------------------------------

section "Python env (tkeir/)"

if ! have "$UV"; then
  fail "skipping Python checks (uv missing)"
else
  if "$UV" python find "$PYTHON" >/dev/null 2>&1; then
    py_path="$("$UV" python find "$PYTHON" 2>/dev/null || true)"
    pass "uv Python ${PYTHON}: ${py_path:-ok}"
  else
    fail "Python ${PYTHON} not available via uv — run: uv python install ${PYTHON}"
  fi

  if [[ -f "${TKEIR_DIR}/pyproject.toml" && -f "${TKEIR_DIR}/uv.lock" ]]; then
    pass "tkeir/pyproject.toml + uv.lock present"
  else
    fail "missing tkeir/pyproject.toml or uv.lock"
  fi

  if [[ -d "${TKEIR_DIR}/.venv" ]]; then
    pass "tkeir/.venv present"
  else
    fail "tkeir/.venv missing — run: make install"
  fi

  thot_out="$(mktemp)"
  thot_err="$(mktemp)"
  if (
    cd "${TKEIR_DIR}" \
      && "$UV" run --no-sync --python "$PYTHON" python -c "import thot; print(thot.__version__)"
  ) >"$thot_out" 2>"$thot_err"; then
    pass "import thot OK (version $(tr -d '\n' <"$thot_out"))"
  else
    fail "cannot import thot — run: make install"
    if [[ -s "$thot_err" ]]; then
      sed 's/^/         /' "$thot_err" | tail -n 5
    fi
  fi
  rm -f "$thot_out" "$thot_err"

  if (
    cd "${TKEIR_DIR}" && "$UV" lock --check
  ) >/dev/null 2>&1; then
    pass "uv.lock in sync with pyproject.toml"
  else
    warn "uv.lock out of sync — run: cd tkeir && uv lock  (or make verify-lockfile)"
  fi
fi

# ---------------------------------------------------------------------------
# spaCy models
# ---------------------------------------------------------------------------

section "spaCy models"

if [[ "$SKIP_SPACY" == "1" ]]; then
  warn "spaCy checks skipped (SKIP_SPACY=1)"
elif ! have "$UV" || [[ ! -d "${TKEIR_DIR}/.venv" ]]; then
  fail "cannot check spaCy models (uv/venv missing)"
else
  models_out="$(
    cd "${TKEIR_DIR}" && "$UV" run --no-sync --python "$PYTHON" python - <<'PY' 2>/dev/null || true
import importlib.util
models = [
    "en_core_web_sm",
    "en_core_web_md",
    "fr_core_news_sm",
    "fr_core_news_md",
    "xx_ent_wiki_sm",
]
missing = [m for m in models if importlib.util.find_spec(m) is None]
print("MISSING=" + ",".join(missing))
print("PRESENT=" + ",".join(m for m in models if importlib.util.find_spec(m) is not None))
PY
  )"
  missing="$(printf '%s\n' "$models_out" | sed -n 's/^MISSING=//p' | tail -n 1)"
  present="$(printf '%s\n' "$models_out" | sed -n 's/^PRESENT=//p' | tail -n 1)"
  if [[ -z "$missing" ]]; then
    pass "spaCy models: ${present:-all}"
  else
    fail "spaCy models missing: ${missing} — run: make install-spacy-models"
    [[ -n "$present" ]] && warn "spaCy models present: ${present}"
  fi
fi

# ---------------------------------------------------------------------------
# Modeling artifacts
# ---------------------------------------------------------------------------

section "Models / resources"

mwe="${TKEIR_DIR}/resources/modeling/tokenizer/en/tkeir_mwe.pkl"
if [[ -f "$mwe" ]]; then
  pass "MWE resource: $mwe"
else
  warn "MWE resource missing — run: make init-models"
fi

bge_dir="${TKEIR_DIR}/resources/modeling/net"
if [[ -d "$bge_dir" ]] && find "$bge_dir" -type f >/dev/null 2>&1 \
  && [[ -n "$(find "$bge_dir" -type f 2>/dev/null | head -n 1)" ]]; then
  pass "embedding model cache under resources/modeling/net"
else
  warn "BGE-M3 / embedding cache not found — run: make pull-bge-model"
fi

# ---------------------------------------------------------------------------
# HMI
# ---------------------------------------------------------------------------

section "HMI (tkeir-hmi)"

if [[ "$SKIP_HMI" == "1" ]]; then
  warn "HMI package checks skipped (SKIP_HMI=1)"
elif [[ ! -f "${HMI_DIR}/package.json" ]]; then
  fail "missing ${HMI_DIR}/package.json"
else
  pass "tkeir-hmi/package.json present"
  if [[ -d "${HMI_DIR}/node_modules" ]]; then
    pass "tkeir-hmi/node_modules present"
  else
    warn "tkeir-hmi/node_modules missing — run: make hmi-install  (or cd tkeir-hmi && npm ci)"
  fi
fi

# ---------------------------------------------------------------------------
# Docker images (soft)
# ---------------------------------------------------------------------------

section "Docker images (optional)"

if [[ "$SKIP_DOCKER" == "1" ]] || ! have docker || ! docker info >/dev/null 2>&1; then
  warn "skipping image checks"
else
  vespa_image="${VESPA_IMAGE:-vespaengine/vespa}"
  if docker image inspect "$vespa_image" >/dev/null 2>&1; then
    pass "Vespa image present: $vespa_image"
  else
    warn "Vespa image not pulled yet: $vespa_image — run: make pull-vespa"
  fi
fi

# ---------------------------------------------------------------------------
# Repo layout / demo helpers
# ---------------------------------------------------------------------------

section "Repository layout"

for path in Makefile tkeir/thot tkeir-hmi deploy start_services.sh; do
  if [[ -e "${ROOT}/${path}" ]]; then
    pass "${path}"
  else
    if [[ "$path" == "start_services.sh" ]]; then
      warn "missing ${path} (optional demo orchestrator)"
    else
      fail "missing ${path}"
    fi
  fi
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

printf '\n== Summary ==\n'
printf '  OK=%s  WARN=%s  FAIL=%s\n' "$OK" "$WARN" "$FAIL"

if [[ "$FAIL" -gt 0 ]]; then
  printf '\n%s\n' "$(red "check-install FAILED") — fix FAIL items (typically: make install && make install-spacy-models && make hmi-install)"
  exit 1
fi

if [[ "$STRICT" == "1" && "$WARN" -gt 0 ]]; then
  printf '\n%s\n' "$(yellow "check-install FAILED (STRICT=1)") — warnings treated as errors"
  exit 1
fi

printf '\n%s\n' "$(green "check-install OK") — local/dev install looks healthy"
if [[ "$WARN" -gt 0 ]]; then
  printf '  (%s warning(s) — optional components or deferred downloads)\n' "$WARN"
fi
exit 0
