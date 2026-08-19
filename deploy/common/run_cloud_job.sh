#!/usr/bin/env bash
set -euo pipefail

: "${JOB_KIND:?JOB_KIND is required}"
: "${RUN_ID:?RUN_ID is required}"
: "${HF_BUCKET:?HF_BUCKET is required}"

export HF_ROOT="${HF_ROOT:-/mnt/hf}"
export HF_HOME="${HF_HOME:-/workspace/cache/huggingface}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$HF_HOME}"
export NEMO_CACHE_DIR="${NEMO_CACHE_DIR:-/workspace/cache/nemo}"
export TORCH_HOME="${TORCH_HOME:-/workspace/cache/torch}"
export PROVIDER="${PROVIDER:-unknown}"

mkdir -p /workspace/cache /workspace/checkpoints-local

/app/deploy/common/mount_hf.sh

RUN_ROOT="$HF_ROOT/runs/$RUN_ID"
mkdir -p "$RUN_ROOT"

cat > "$RUN_ROOT/environment.json" <<EOF
{
  "run_id": "$RUN_ID",
  "provider": "$PROVIDER",
  "job_kind": "$JOB_KIND",
  "git_sha": "${GIT_SHA:-unknown}",
  "image": "${IMAGE_REF:-unknown}",
  "parakeet_model": "${PARAKEET_MODEL:-nvidia/parakeet-tdt_ctc-0.6b-ja}",
  "stepaudio_model": "${STEPAUDIO_MODEL:-stepfun-ai/Step-Audio-2-mini}"
}
EOF

status=0

case "$JOB_KIND" in
  smoke)
    python /app/scripts/check_environment.py | tee "$RUN_ROOT/environment-check.json"
    ;;

  teacher)
    : "${AUDIO_REL:?AUDIO_REL is required}"
    : "${SEGMENTS_REL:?SEGMENTS_REL is required}"

    python /app/scripts/run_teacher.py \
      --audio "$HF_ROOT/$AUDIO_REL" \
      --segments "$HF_ROOT/$SEGMENTS_REL" \
      --output "$RUN_ROOT/teacher.parquet" \
      --model "${STEPAUDIO_MODEL:-stepfun-ai/Step-Audio-2-mini}"
    ;;

  context-train)
    : "${TRAIN_REL:?TRAIN_REL is required}"
    : "${VALID_REL:?VALID_REL is required}"

    python /app/scripts/train_context.py \
      --train "$HF_ROOT/$TRAIN_REL" \
      --valid "$HF_ROOT/$VALID_REL" \
      --output-dir /workspace/checkpoints-local/context \
      --epochs "${EPOCHS:-10}"

    mkdir -p "$RUN_ROOT/checkpoints/context"
    cp -a /workspace/checkpoints-local/context/. "$RUN_ROOT/checkpoints/context/"
    ;;

  editorial-train)
    : "${TRAIN_REL:?TRAIN_REL is required}"
    : "${VALID_REL:?VALID_REL is required}"

    python /app/scripts/train_editorial.py \
      --train "$HF_ROOT/$TRAIN_REL" \
      --valid "$HF_ROOT/$VALID_REL" \
      --output-dir /workspace/checkpoints-local/editorial \
      --epochs "${EPOCHS:-10}"

    mkdir -p "$RUN_ROOT/checkpoints/editorial"
    cp -a /workspace/checkpoints-local/editorial/. "$RUN_ROOT/checkpoints/editorial/"
    ;;

  *)
    echo "Unknown JOB_KIND=$JOB_KIND" >&2
    status=2
    ;;
esac

if [ "$status" -eq 0 ]; then
  cat > "$RUN_ROOT/_SUCCESS.json" <<EOF
{"run_id":"$RUN_ID","provider":"$PROVIDER","job_kind":"$JOB_KIND","status":"success"}
EOF
else
  cat > "$RUN_ROOT/_FAILED.json" <<EOF
{"run_id":"$RUN_ID","provider":"$PROVIDER","job_kind":"$JOB_KIND","status":"failed","exit_code":$status}
EOF
fi

exit "$status"
