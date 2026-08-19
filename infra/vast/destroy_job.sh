#!/usr/bin/env bash
set -euo pipefail
: "${VAST_API_KEY:?VAST_API_KEY is required}"
: "${1:?instance id is required}"

python -m pip install --quiet --upgrade vastai
vastai destroy instance "$1" --api-key "$VAST_API_KEY"
