#!/usr/bin/env bash
# Entrypoint for tkeir-indexer — wraps pipeline and/or document indexing.
set -euo pipefail

PIPELINE_CONFIG="${PIPELINE_CONFIG:-/opt/tkeir/configs/pipeline.yaml}"
PIPELINE_INPUT="${PIPELINE_INPUT:-/data/in}"
PIPELINE_OUTPUT="${PIPELINE_OUTPUT:-/data/out}"
PIPELINE_TYPE="${PIPELINE_TYPE:-auto}"
INDEX_INPUT="${INDEX_INPUT:-/data/out}"

usage() {
  cat <<'EOF'
tkeir-indexer commands:
  help              Show this help
  pipeline          Run tkeir-pipeline (PIPELINE_* env)
  index             Run tkeir-index-documents (INDEX_INPUT)
  pipeline-index    pipeline then index (default worker flow)
  shell             Interactive bash

Environment:
  PIPELINE_CONFIG  default /opt/tkeir/configs/pipeline.yaml
  PIPELINE_INPUT   default /data/in
  PIPELINE_OUTPUT  default /data/out
  PIPELINE_TYPE    default auto
  INDEX_INPUT      default /data/out (= PIPELINE_OUTPUT)
  VESPA_URL, PROVIDER, EMBEDDING_MODEL, OLLAMA_BASE_URL, …
EOF
}

cmd="${1:-help}"
shift || true

case "${cmd}" in
  help|-h|--help)
    usage
    ;;
  pipeline)
    mkdir -p "${PIPELINE_OUTPUT}"
    exec tkeir-pipeline \
      -c "${PIPELINE_CONFIG}" \
      -i "${PIPELINE_INPUT}" \
      -o "${PIPELINE_OUTPUT}" \
      -t "${PIPELINE_TYPE}" \
      "$@"
    ;;
  index)
    exec tkeir-index-documents --input "${INDEX_INPUT}" "$@"
    ;;
  pipeline-index)
    mkdir -p "${PIPELINE_OUTPUT}"
    tkeir-pipeline \
      -c "${PIPELINE_CONFIG}" \
      -i "${PIPELINE_INPUT}" \
      -o "${PIPELINE_OUTPUT}" \
      -t "${PIPELINE_TYPE}"
    exec tkeir-index-documents --input "${PIPELINE_OUTPUT}" "$@"
    ;;
  shell)
    exec /bin/bash "$@"
    ;;
  *)
    echo "unknown command: ${cmd}" >&2
    usage >&2
    exit 2
    ;;
esac
