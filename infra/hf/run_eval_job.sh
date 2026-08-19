#!/usr/bin/env bash
set -euo pipefail

: "${HF_TOKEN:?HF_TOKEN is required}"
: "${HF_BUCKET:?HF_BUCKET is required}"
: "${EVAL_IMAGE:?EVAL_IMAGE is required}"
: "${PREDICTIONS_REL:?PREDICTIONS_REL is required}"
: "${REFERENCES_REL:?REFERENCES_REL is required}"
: "${OUTPUT_REL:?OUTPUT_REL is required}"

python -m pip install --quiet --upgrade "huggingface_hub>=1.8.0"

hf jobs run \
  --flavor "${HF_JOB_FLAVOR:-cpu-upgrade}" \
  --secrets HF_TOKEN="$HF_TOKEN" \
  -v "hf://buckets/$HF_BUCKET:/mnt/hf" \
  "$EVAL_IMAGE" \
  python /app/scripts/evaluate_editorial.py \
    --predictions "/mnt/hf/$PREDICTIONS_REL" \
    --references "/mnt/hf/$REFERENCES_REL" \
    --output "/mnt/hf/$OUTPUT_REL"
