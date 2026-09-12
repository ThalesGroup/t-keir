#!/usr/bin/env bash
# Title: snapshot_index.sh — save/restore the Vespa data volume as a tar archive.
#
# Usage:
#   INDEX_SNAPSHOT=1 ./vespa/snapshot_index.sh save
#   INDEX_SNAPSHOT=1 ./vespa/snapshot_index.sh restore-if-empty
#   INDEX_SNAPSHOT=/path/to/index.tar.gz ./vespa/snapshot_index.sh restore
#   INDEX_SNAPSHOT=1 ./vespa/snapshot_index.sh resolve
#
# INDEX_SNAPSHOT / TKEIR_INDEX_SNAPSHOT:
#   unset, 0, false, no, off  — disabled (resolve prints nothing)
#   1, true, yes, on          — <repo>/.vespa-snapshots/<USECASE>/index.tar.gz
#   any other string          — archive file (or directory → index.tar.gz inside)
#
# save            stop Vespa, tar the volume, leave the container stopped
# restore         stop Vespa, replace volume contents from the archive
# restore-if-empty  restore only when the live volume has no data
# resolve         print the archive path (empty when disabled)
#
# Author: T-KEIR
# Copyright (c) 2026 Thales — MIT License

set -euo pipefail

VESPA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$VESPA_DIR/.." && pwd)"
VESPA_NAME="${VESPA_NAME:-vespa}"
VESPA_IMAGE="${VESPA_IMAGE:-vespaengine/vespa}"
VESPA_VOLUME_MOUNT="${VESPA_VOLUME:-vespa_data:/opt/vespa/var}"
VESPA_VOLUME_NAME="${VESPA_VOLUME_MOUNT%%:*}"
USECASE="${USECASE:-${TKEIR_USECASE:-osint}}"

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

log() {
  printf '[snapshot] %s\n' "$*"
}

snapshot_raw() {
  printf '%s' "${INDEX_SNAPSHOT:-${TKEIR_INDEX_SNAPSHOT:-}}"
}

snapshot_flag_lower() {
  printf '%s' "$(snapshot_raw)" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]'
}

snapshot_disabled() {
  local flag
  flag="$(snapshot_flag_lower)"
  [[ -z "$flag" || "$flag" == "0" || "$flag" == "false" || "$flag" == "no" || "$flag" == "off" ]]
}

snapshot_default_path() {
  local flag
  flag="$(snapshot_flag_lower)"
  [[ "$flag" == "1" || "$flag" == "true" || "$flag" == "yes" || "$flag" == "on" ]]
}

# Absolute archive path, or empty when snapshots are disabled.
resolve_archive() {
  local raw dest
  if snapshot_disabled; then
    return 0
  fi
  if snapshot_default_path; then
    dest="$ROOT/.vespa-snapshots/${USECASE}/index.tar.gz"
  else
    raw="$(snapshot_raw)"
    if [[ "$raw" == /* ]]; then
      dest="$raw"
    else
      dest="$ROOT/$raw"
    fi
    if [[ "$dest" == */ || -d "$dest" ]]; then
      dest="${dest%/}/index.tar.gz"
    fi
  fi
  printf '%s\n' "$dest"
}

container_exists() {
  docker ps -a --format '{{.Names}}' | grep -qx "$VESPA_NAME"
}

stop_vespa() {
  if container_exists; then
    log "stopping container '${VESPA_NAME}' for a consistent snapshot"
    docker stop "$VESPA_NAME" >/dev/null 2>&1 || true
  fi
}

is_bind_mount() {
  [[ "$VESPA_VOLUME_NAME" == /* ]]
}

volume_has_data() {
  if is_bind_mount; then
    [[ -d "$VESPA_VOLUME_NAME" ]] || return 1
    [[ -n "$(ls -A "$VESPA_VOLUME_NAME" 2>/dev/null || true)" ]]
    return
  fi
  docker volume inspect "$VESPA_VOLUME_NAME" >/dev/null 2>&1 || return 1
  docker run --rm --entrypoint /bin/bash \
    -v "${VESPA_VOLUME_NAME}:/vespa-var:ro" \
    "$VESPA_IMAGE" \
    -c '[[ -n "$(ls -A /vespa-var 2>/dev/null || true)" ]]'
}

ensure_volume() {
  if is_bind_mount; then
    mkdir -p "$VESPA_VOLUME_NAME"
    return 0
  fi
  docker volume inspect "$VESPA_VOLUME_NAME" >/dev/null 2>&1 \
    || docker volume create "$VESPA_VOLUME_NAME" >/dev/null
}

write_meta() {
  local archive="$1"
  local meta="${archive}.meta"
  cat >"$meta" <<EOF
usecase=${USECASE}
saved_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
vespa_volume=${VESPA_VOLUME_NAME}
vespa_name=${VESPA_NAME}
EOF
}

run_volume_tar() {
  local mode="$1"
  local archive="$2"
  local host_dir host_file
  host_dir="$(cd "$(dirname "$archive")" && pwd)"
  host_file="$(basename "$archive")"

  if is_bind_mount; then
    case "$mode" in
      save)
        tar -C "$VESPA_VOLUME_NAME" -czf "$archive" .
        ;;
      restore)
        find "$VESPA_VOLUME_NAME" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
        tar -C "$VESPA_VOLUME_NAME" -xzf "$archive"
        ;;
      *)
        die "unknown tar mode: $mode"
        ;;
    esac
    return 0
  fi

  case "$mode" in
    save)
      docker run --rm --user root --entrypoint /bin/bash \
        -v "${VESPA_VOLUME_NAME}:/vespa-var:ro" \
        -v "${host_dir}:/backup" \
        "$VESPA_IMAGE" \
        -c "tar -C /vespa-var -czf /backup/$(printf '%q' "$host_file") ."
      chown "$(id -u):$(id -g)" "$archive" 2>/dev/null || true
      ;;
    restore)
      docker run --rm --user root --entrypoint /bin/bash \
        -v "${VESPA_VOLUME_NAME}:/vespa-var" \
        -v "${host_dir}:/backup:ro" \
        "$VESPA_IMAGE" \
        -c "find /vespa-var -mindepth 1 -maxdepth 1 -exec rm -rf {} +
            tar -C /vespa-var -xzf /backup/$(printf '%q' "$host_file")
            if id vespa >/dev/null 2>&1; then chown -R vespa:vespa /vespa-var; fi"
      ;;
    *)
      die "unknown tar mode: $mode"
      ;;
  esac
}

cmd_save() {
  local archive="$1"
  if [[ -z "$archive" ]]; then
    log "INDEX_SNAPSHOT disabled — skip save"
    return 0
  fi
  command -v docker >/dev/null 2>&1 || die "docker is required to save the Vespa index"
  if is_bind_mount; then
    if [[ ! -d "$VESPA_VOLUME_NAME" ]]; then
      log "Vespa bind mount not found (${VESPA_VOLUME_NAME}) — skip save"
      return 0
    fi
  else
    if ! docker volume inspect "$VESPA_VOLUME_NAME" >/dev/null 2>&1; then
      log "Vespa volume '${VESPA_VOLUME_NAME}' not found — skip save"
      return 0
    fi
  fi
  if ! volume_has_data; then
    log "Vespa volume '${VESPA_VOLUME_NAME}' is empty — skip save"
    return 0
  fi
  mkdir -p "$(dirname "$archive")"
  stop_vespa
  log "saving '${VESPA_VOLUME_NAME}' → ${archive}"
  run_volume_tar save "$archive"
  write_meta "$archive"
  log "saved $(du -h "$archive" | awk '{print $1}') to ${archive}"
}

cmd_restore() {
  local archive="$1"
  [[ -n "$archive" ]] || die "INDEX_SNAPSHOT is unset — set INDEX_SNAPSHOT=1 or a path"
  [[ -f "$archive" ]] || die "snapshot not found: $archive"
  command -v docker >/dev/null 2>&1 || die "docker is required to restore the Vespa index"
  stop_vespa
  ensure_volume
  log "restoring ${archive} → '${VESPA_VOLUME_NAME}'"
  run_volume_tar restore "$archive"
  log "restored Vespa index from ${archive}"
}

cmd_restore_if_empty() {
  local archive="$1"
  if [[ -z "$archive" ]]; then
    log "INDEX_SNAPSHOT disabled — skip restore"
    return 0
  fi
  if [[ ! -f "$archive" ]]; then
    log "no snapshot at ${archive} — starting with an empty index"
    return 0
  fi
  if container_exists; then
    log "container '${VESPA_NAME}' already exists — keep live index (not restoring ${archive})"
    return 0
  fi
  if volume_has_data; then
    log "volume '${VESPA_VOLUME_NAME}' already has data — keep live index (not restoring ${archive})"
    return 0
  fi
  cmd_restore "$archive"
}

usage() {
  sed -n '1,24p' "$0"
}

main() {
  local action="${1:-}"
  local archive
  case "$action" in
    resolve)
      resolve_archive
      ;;
    save|restore|restore-if-empty)
      archive="$(resolve_archive)"
      if [[ "$action" == "save" ]]; then
        cmd_save "$archive"
      elif [[ "$action" == "restore" ]]; then
        cmd_restore "$archive"
      else
        cmd_restore_if_empty "$archive"
      fi
      ;;
    -h|--help|help|"")
      usage
      [[ -n "$action" && "$action" != "help" && "$action" != "-h" && "$action" != "--help" ]] \
        && exit 1
      ;;
    *)
      die "unknown action: $action (save|restore|restore-if-empty|resolve)"
      ;;
  esac
}

main "$@"
