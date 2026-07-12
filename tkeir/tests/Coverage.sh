#!/bin/bash
# Full coverage run delegates to the scoped fast suite used in CI.
script_path=$(dirname "$0")
exec bash "$script_path/CoverageFast.sh"
