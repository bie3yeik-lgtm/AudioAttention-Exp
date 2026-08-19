#!/usr/bin/env bash
set -euo pipefail

: "${VAST_API_KEY:?VAST_API_KEY is required}"
: "${VAST_GPU_QUERY:?VAST_GPU_QUERY is required}"
: "${VAST_DISK_GB:?VAST_DISK_GB is required}"

if ! [[ "$VAST_DISK_GB" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "VAST_DISK_GB must be a positive number: $VAST_DISK_GB" >&2
  exit 2
fi

python - "$VAST_DISK_GB" <<'PY'
import sys
v = float(sys.argv[1])
if v <= 0:
    raise SystemExit("VAST_DISK_GB must be > 0")
PY

python -m pip install --quiet --upgrade vastai

# --storage affects quoted total price, but does not itself guarantee capacity.
# Add an explicit disk_space filter so the selected offer can allocate VAST_DISK_GB.
query="${VAST_GPU_QUERY} disk_space>=${VAST_DISK_GB}"

set +e
raw="$(
  vastai search offers "$query" \
    --order=dph_total \
    --storage "$VAST_DISK_GB" \
    --limit 20 \
    --raw \
    --api-key "$VAST_API_KEY" 2>/tmp/vast-search.err
)"
rc=$?
set -e

if [ "$rc" -ne 0 ]; then
  echo "Vast offer query is invalid or Vast search failed." >&2
  cat /tmp/vast-search.err >&2 || true
  exit 3
fi

python - "$raw" <<'PY'
import json
import sys

raw = sys.argv[1]
try:
    offers = json.loads(raw)
except json.JSONDecodeError as exc:
    print(f"Vast returned invalid JSON: {exc}", file=sys.stderr)
    raise SystemExit(4)

if isinstance(offers, dict):
    # Be tolerant of an API-like wrapper if the CLI changes shape.
    offers = offers.get("offers", [])

if not isinstance(offers, list):
    print(f"Unexpected Vast response type: {type(offers).__name__}", file=sys.stderr)
    raise SystemExit(4)

if not offers:
    # Exit 10 means: query valid, but no currently usable offer.
    raise SystemExit(10)

offer = offers[0]

required = ("id",)
missing = [k for k in required if k not in offer]
if missing:
    print(f"Vast offer missing required fields: {missing}", file=sys.stderr)
    raise SystemExit(4)

print(json.dumps({
    "offer_id": offer["id"],
    "gpu_name": offer.get("gpu_name"),
    "gpu_ram": offer.get("gpu_ram"),
    "dph_total": offer.get("dph_total", offer.get("dph")),
    "reliability": offer.get("reliability"),
    "disk_space": offer.get("disk_space"),
}, ensure_ascii=False))
PY
