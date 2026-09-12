#!/bin/sh
# Verify a built T-KEIR image has the MWE pickle and/or usecase artefacts.
# Usage: verify-image.sh <image> [lib|indexer|hmi]
set -eu

image="${1:?image reference required}"
kind="${2:-lib}"

case "${kind}" in
  lib)
    docker run --rm --entrypoint sh "${image}" -c '
      set -eu
      pkl=/opt/tkeir/resources/modeling/tokenizer/any/tkeir_mwe.pkl
      test -s "$pkl"
      size=$(wc -c < "$pkl")
      test "$size" -gt 1000000
      test -d /opt/tkeir/packs/osint/agents
      test -d /opt/tkeir/packs/osint/workflows
      test -f /opt/tkeir/packs/osint/agent_orchestrator.yaml
      test -f /opt/tkeir/packs/osint/business_ontology.yaml
      test -d /opt/tkeir/packs/enterprise/agents
      test -f /opt/tkeir/packs/enterprise/enterprise_ontology.yaml
      test -d /opt/tkeir/resources/modeling/spacy
      echo "ok lib pickle=${size}B packs=osint,enterprise"
    '
    ;;
  indexer)
    docker run --rm --entrypoint sh "${image}" -c '
      set -eu
      pkl=/opt/tkeir/resources/modeling/tokenizer/any/tkeir_mwe.pkl
      test -s "$pkl"
      size=$(wc -c < "$pkl")
      test "$size" -gt 1000000
      echo "ok indexer pickle=${size}B"
    '
    ;;
  hmi)
    docker run --rm --entrypoint sh "${image}" -c '
      set -eu
      test -s /app/public/usecase.json
      echo "ok hmi usecase.json"
    '
    ;;
  *)
    echo "error: unknown kind '${kind}' (lib|indexer|hmi)" >&2
    exit 1
    ;;
esac
