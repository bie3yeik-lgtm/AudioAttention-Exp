#!/usr/bin/env bash
set -euo pipefail

: "${VAST_API_KEY:?VAST_API_KEY is required}"
: "${IMAGE_REF:?IMAGE_REF is required}"
: "${JOB_KIND:?JOB_KIND is required}"
: "${RUN_ID:?RUN_ID is required}"
: "${HF_TOKEN:?HF_TOKEN is required}"
: "${HF_BUCKET:?HF_BUCKET is required}"

GPU_QUERY="${VAST_GPU_QUERY:-gpu_ram>=48000 num_gpus=1 reliability>0.98 verified=true rentable=true}"
DISK_GB="${VAST_DISK_GB:-150}"
LABEL="${VAST_LABEL:-audio-editorial-${JOB_KIND}-${RUN_ID}}"

python -m pip install --quiet --upgrade vastai

offers="$(vastai search offers "$GPU_QUERY" --order=dph_total --storage "$DISK_GB" --raw --api-key "$VAST_API_KEY")"

offer_id="$(
python - "$offers" <<'PY'
import json, sys
obj=json.loads(sys.argv[1])
if not obj:
    raise SystemExit("No Vast offer matched")
print(obj[0]["id"])
PY
)"

env_args=(
  "-e HF_TOKEN=$HF_TOKEN"
  "-e HF_BUCKET=$HF_BUCKET"
  "-e HF_ROOT=${HF_ROOT:-/mnt/hf}"
  "-e HF_HOME=${HF_HOME:-/workspace/cache/huggingface}"
  "-e NEMO_CACHE_DIR=${NEMO_CACHE_DIR:-/workspace/cache/nemo}"
  "-e TORCH_HOME=${TORCH_HOME:-/workspace/cache/torch}"
  "-e JOB_KIND=$JOB_KIND"
  "-e RUN_ID=$RUN_ID"
  "-e PROVIDER=vast"
  "-e GIT_SHA=${GIT_SHA:-unknown}"
  "-e IMAGE_REF=$IMAGE_REF"
  "-e PARAKEET_MODEL=${PARAKEET_MODEL:-nvidia/parakeet-tdt_ctc-0.6b-ja}"
  "-e STEPAUDIO_MODEL=${STEPAUDIO_MODEL:-stepfun-ai/Step-Audio-2-mini}"
)

for k in AUDIO_REL SEGMENTS_REL TRAIN_REL VALID_REL EPOCHS; do
  if [ -n "${!k:-}" ]; then
    env_args+=("-e $k=${!k}")
  fi
done

env_string="${env_args[*]}"

result="$(
  vastai create instance "$offer_id" \
    --image "$IMAGE_REF" \
    --disk "$DISK_GB" \
    --label "$LABEL" \
    --env "$env_string" \
    --entrypoint "/bin/bash" \
    --args "-lc /app/deploy/common/run_cloud_job.sh" \
    --raw \
    --api-key "$VAST_API_KEY"
)"

instance_id="$(
python - "$result" <<'PY'
import json, sys
obj=json.loads(sys.argv[1])
for key in ("new_contract", "id", "instance_id"):
    if key in obj:
        print(obj[key])
        break
else:
    raise SystemExit(f"Could not find instance id in: {obj}")
PY
)"

echo "$instance_id"
