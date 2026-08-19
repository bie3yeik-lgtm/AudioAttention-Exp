#!/usr/bin/env bash
set -euo pipefail

: "${RUNPOD_REGISTRY_ID:?RUNPOD_REGISTRY_ID is required}"

IMAGE="${IMAGE:-ghcr.io/YOUR_ORG/audio-editorial-train:0.1.0}"

runpodctl template create \
  --name "audio-editorial-train" \
  --image "$IMAGE" \
  --registry-auth-id "$RUNPOD_REGISTRY_ID" \
  --container-disk-in-gb 80 \
  --volume-in-gb 150 \
  --volume-mount-path "/workspace" \
  --ports "22/tcp,8888/http" \
  --port-labels "22=ssh,8888=jupyter" \
  --env '{
    "HF_TOKEN":"{{ RUNPOD_SECRET_huggingface_token }}",
    "HF_BUCKET":"YOUR_ORG/audio-editorial-data",
    "HF_DATASET":"YOUR_ORG/audio-editorial-dataset",
    "HF_ROOT":"/mnt/hf",
    "HF_HOME":"/workspace/cache/huggingface",
    "NEMO_CACHE_DIR":"/workspace/cache/nemo",
    "PARAKEET_MODEL":"nvidia/parakeet-tdt_ctc-0.6b-ja",
    "STEPAUDIO_MODEL":"stepfun-ai/Step-Audio-2-mini"
  }'
