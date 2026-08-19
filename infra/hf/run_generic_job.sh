#!/usr/bin/env bash
set -euo pipefail

: "${HF_TOKEN:?HF_TOKEN is required}"
: "${HF_BUCKET:?HF_BUCKET is required}"
: "${HF_JOB_IMAGE:?HF_JOB_IMAGE is required}"
: "${HF_JOB_FLAVOR:?HF_JOB_FLAVOR is required}"
: "${HF_JOB_COMMAND:?HF_JOB_COMMAND is required}"

namespace_args=()
if [ -n "${HF_NAMESPACE:-}" ]; then
  namespace_args+=(--namespace "$HF_NAMESPACE")
fi

python -m pip install --quiet --upgrade "huggingface_hub>=1.8.0"

# Use --detach so GitHub Actions only orchestrates submission.
# Outputs are written directly to the mounted HF Bucket.
job_id="$(
  hf jobs run \
    --detach \
    --flavor "$HF_JOB_FLAVOR" \
    "${namespace_args[@]}" \
    --secrets HF_TOKEN="$HF_TOKEN" \
    -v "hf://buckets/$HF_BUCKET:/mnt/hf" \
    "$HF_JOB_IMAGE" \
    bash -lc "$HF_JOB_COMMAND"
)"

echo "$job_id"
