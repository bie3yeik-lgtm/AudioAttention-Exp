#!/usr/bin/env bash
set -euo pipefail

: "${HF_TOKEN:?HF_TOKEN is required}"
: "${HF_BUCKET:?HF_BUCKET is required}"

HF_ROOT="${HF_ROOT:-/mnt/hf}"
HF_MOUNT_CACHE_DIR="${HF_MOUNT_CACHE_DIR:-/workspace/cache/hf-mount}"
HF_MOUNT_CACHE_SIZE="${HF_MOUNT_CACHE_SIZE:-30000000000}"

mkdir -p "$HF_ROOT" "$HF_MOUNT_CACHE_DIR"

if ! command -v hf-mount >/dev/null 2>&1; then
  echo "[mount_hf] installing hf-mount"
  curl -fsSL https://raw.githubusercontent.com/huggingface/hf-mount/main/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

hf-mount stop "$HF_ROOT" >/dev/null 2>&1 || true

hf-mount start \
  --hf-token "$HF_TOKEN" \
  --cache-dir "$HF_MOUNT_CACHE_DIR" \
  --cache-size "$HF_MOUNT_CACHE_SIZE" \
  bucket "$HF_BUCKET" \
  "$HF_ROOT"

hf-mount status
