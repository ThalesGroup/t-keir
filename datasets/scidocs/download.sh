#!/usr/bin/env bash
# Download BEIR SciDocs into this directory (corpus / queries / qrels).
# Keeps committed files (business_ontology.yaml, this script) in place.
#
# Usage (from repo root or here):
#   bash datasets/scidocs/download.sh
#   make scidocs-download
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATASETS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NAME="scidocs"
URL="${SCIDOCS_URL:-https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scidocs.zip}"
ZIP="${DATASETS_DIR}/${NAME}.zip"
MARKER="${SCRIPT_DIR}/corpus.jsonl"
FORCE="${FORCE_SCIDOCS:-0}"

if [ -f "${MARKER}" ] && [ "${FORCE}" != "1" ]; then
  echo "SciDocs already present at ${SCRIPT_DIR}"
  echo "  corpus : ${MARKER}"
  echo "  Set FORCE_SCIDOCS=1 to re-download."
  exit 0
fi

mkdir -p "${SCRIPT_DIR}" "${DATASETS_DIR}"

echo "Downloading SciDocs from ${URL}"
echo "  → ${ZIP}"
if command -v curl >/dev/null 2>&1; then
  curl -fL --retry 3 --retry-delay 2 -o "${ZIP}" "${URL}"
elif command -v wget >/dev/null 2>&1; then
  wget -O "${ZIP}" "${URL}"
else
  echo "ERROR: need curl or wget" >&2
  exit 1
fi

echo "Extracting into ${DATASETS_DIR}/ (preserves business_ontology.yaml)…"
# Zip layout: scidocs/{corpus.jsonl,queries.jsonl,qrels/…}
unzip -o "${ZIP}" -d "${DATASETS_DIR}"

if [ ! -f "${MARKER}" ]; then
  echo "ERROR: ${MARKER} missing after unzip" >&2
  exit 1
fi

# Drop the zip (gitignored); keep ontology + download script.
rm -f "${ZIP}"

echo "Done."
echo "  corpus  : $(wc -l < "${MARKER}" | tr -d ' ') lines"
echo "  queries : $(wc -l < "${SCRIPT_DIR}/queries.jsonl" | tr -d ' ') lines"
echo "  qrels   : ${SCRIPT_DIR}/qrels/"
echo "  ontology: ${SCRIPT_DIR}/business_ontology.yaml"
