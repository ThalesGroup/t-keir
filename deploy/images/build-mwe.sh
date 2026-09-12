#!/bin/sh
# Build tokenizer MWE trie into the image. Always regenerates so gazetteer
# updates (OTAN lists, geo, …) are not skipped because a host pickle existed.
set -eu

resources_any="${1:-/opt/tkeir/resources/modeling/tokenizer/any}"
out="${resources_any}/tkeir_mwe.pkl"
entries="${resources_any}/annotation-resources.json"

if [ ! -f "${entries}" ]; then
  echo "error: annotation catalog missing: ${entries}" >&2
  exit 1
fi

rm -f "${out}"
tkeir-create-annotation-resource \
  --entries-file "${entries}" \
  --output "${out}"

if [ ! -s "${out}" ]; then
  echo "error: MWE pickle was not created: ${out}" >&2
  exit 1
fi

echo "Built MWE trie at ${out} ($(wc -c < "${out}") bytes)"
