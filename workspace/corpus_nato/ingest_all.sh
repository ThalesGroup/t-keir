#!/usr/bin/env sh
set -eu
# Example: replace this command with the local T-KEIR ingest invocation.
find "$(dirname "$0")"/ontologies -type f \( -name '*.owl' -o -name '*.ttl' \) -print
