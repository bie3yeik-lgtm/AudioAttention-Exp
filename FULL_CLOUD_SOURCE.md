# Full GitHub / Runpod / Vast source

## `docs/architecture.md`

```markdown
# Cloud architecture

```text
                         GitHub
                           |
               +-----------+-----------+
               |                       |
             Actions                  GHCR
               |               immutable Docker images
               |
      +--------+--------+
      |                 |
   Runpod              Vast
  stable GPU        marketplace GPU
      |                 |
      +--------+--------+
               |
            /mnt/hf
               |
        Hugging Face Bucket
        single source of truth
               |
        +------+------+
        |             |
      data          results
        |             |
        +------HF Jobs+
          deterministic
          evaluation
```

Responsibilities:

- GitHub: source, CI/CD, orchestration.
- GHCR: immutable execution images identified by digest/SHA.
- HF Bucket: raw audio, derived data, labels, checkpoints, run outputs.
- Runpod: stable interactive/teacher/training capacity.
- Vast: low-cost/fallback/batch capacity.
- HF Jobs: deterministic dataset validation and golden evaluation.

```

## `docs/github-setup.md`

```markdown
# GitHub setup

## Repository variables

Repository or Environment variables:

```text
HF_BUCKET=YOUR_ORG/audio-editorial-data

RUNPOD_CLOUD_TYPE=SECURE
RUNPOD_REGISTRY_AUTH_ID=<optional Runpod registry auth ID>

VAST_GPU_QUERY=gpu_ram>=48000 num_gpus=1 reliability>0.98 verified=true rentable=true
VAST_DISK_GB=150
```

## Secrets

```text
HF_TOKEN
RUNPOD_API_KEY
VAST_API_KEY
```

If GHCR packages are private, Runpod also needs a registry auth entry that can pull
`ghcr.io/<org>/audio-editorial-*`.

Vast must likewise be able to pull the image. The simplest configuration for a
research repository is to make the runtime GHCR packages public while keeping
source/data private. If private images are required, add a scoped GHCR pull token
to Vast's image/instance configuration rather than embedding it in source.

## Environments

Create:

```text
gpu-runpod
gpu-vast
hf-evaluation
release
```

Recommended protection:

- `gpu-runpod`: required reviewer
- `gpu-vast`: required reviewer
- `release`: required reviewer
- `hf-evaluation`: no reviewer needed for routine validation

This makes accidental paid GPU launches harder.

## Branches

Recommended:

```text
main       release-quality branch
develop    integration branch
feature/*  normal work
```

PRs target `develop`; release PRs merge `develop -> main`.

## GHCR convention

```text
ghcr.io/<org>/audio-editorial-stepaudio:sha-<40-char-sha>
ghcr.io/<org>/audio-editorial-train:sha-<40-char-sha>
ghcr.io/<org>/audio-editorial-eval:sha-<40-char-sha>
ghcr.io/<org>/audio-editorial-parakeet:sha-<40-char-sha>
```

Use the SHA tag in Runpod/Vast jobs. `main` is only a convenience tag.

## HF artifact convention

```text
runs/<provider>-<github-run-id>-<attempt>/
  environment.json
  ...
  _SUCCESS.json
```

Never let multiple workers overwrite a shared `latest.parquet`.

```

## `infra/README.md`

```markdown
# Cloud infrastructure

## Contract

Both Runpod and Vast execute the same immutable GHCR image and write durable
artifacts to the same Hugging Face Storage Bucket.

Common paths:

```text
HF_ROOT=/mnt/hf
/workspace/cache            provider-local cache
/mnt/hf/runs/<RUN_ID>/      durable per-run result
```

Do not use HF Storage Buckets as a distributed lock. Use unique `RUN_ID`s.

## Runpod

CI uses the official REST API under `https://rest.runpod.io/v1`.
For local interactive administration you can also use `runpodctl`.

```bash
bash <(curl -sL cli.runpod.io)
runpodctl config --apiKey "$RUNPOD_API_KEY"
runpodctl gpu list
runpodctl pod list --all
```

## Vast

```bash
pip install --upgrade vastai
vastai set api-key "$VAST_API_KEY"

vastai search offers \
  'gpu_ram>=48000 num_gpus=1 reliability>0.98 verified=true rentable=true' \
  --order=dph_total

vastai show instances
```

## Hugging Face

HF Jobs is used for deterministic validation and golden evaluation.

```bash
pip install --upgrade 'huggingface_hub>=1.8.0'
hf jobs run \
  -v hf://buckets/YOUR_ORG/audio-editorial-data:/mnt/hf \
  IMAGE COMMAND...
```

```

## `deploy/common/mount_hf.sh`

```bash
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

```

## `deploy/common/run_cloud_job.sh`

```bash
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

```

## `infra/runpod/create_job.py`

```python
#!/usr/bin/env python3
"""
Create a one-shot Runpod Pod using the official REST API.

The Pod starts /app/deploy/common/run_cloud_job.sh and is expected to write
its durable outputs to hf://buckets/<HF_BUCKET>/runs/<RUN_ID>/.

This command prints the Pod ID to stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request


API = "https://rest.runpod.io/v1"


def request(method: str, path: str, token: str, payload=None):
    data = None
    headers = {"Authorization": f"Bearer {token}"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(req) as resp:
        body = resp.read()
        return json.loads(body) if body else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--gpu", action="append", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--cloud-type", default="SECURE", choices=["SECURE", "COMMUNITY"])
    parser.add_argument("--container-disk", type=int, default=100)
    parser.add_argument("--volume", type=int, default=150)
    parser.add_argument("--interruptible", action="store_true")
    parser.add_argument("--registry-auth-id")
    args = parser.parse_args()

    token = os.environ["RUNPOD_API_KEY"]

    env_names = [
        "HF_TOKEN",
        "HF_BUCKET",
        "HF_ROOT",
        "HF_HOME",
        "NEMO_CACHE_DIR",
        "TORCH_HOME",
        "HF_MOUNT_CACHE_DIR",
        "HF_MOUNT_CACHE_SIZE",
        "JOB_KIND",
        "RUN_ID",
        "GIT_SHA",
        "IMAGE_REF",
        "PARAKEET_MODEL",
        "STEPAUDIO_MODEL",
        "AUDIO_REL",
        "SEGMENTS_REL",
        "TRAIN_REL",
        "VALID_REL",
        "EPOCHS",
    ]
    env = {k: os.environ[k] for k in env_names if os.environ.get(k)}
    env["PROVIDER"] = "runpod"

    payload = {
        "name": args.name,
        "imageName": args.image,
        "gpuTypeIds": args.gpu,
        "gpuTypePriority": "availability",
        "gpuCount": 1,
        "cloudType": args.cloud_type,
        "computeType": "GPU",
        "containerDiskInGb": args.container_disk,
        "volumeInGb": args.volume,
        "volumeMountPath": "/workspace",
        "interruptible": args.interruptible,
        "allowedCudaVersions": ["13.0", "12.9", "12.8", "12.7", "12.6", "12.5", "12.4", "12.3", "12.2", "12.1"],
        "env": env,
        "dockerEntrypoint": ["/bin/bash", "-lc"],
        "dockerStartCmd": ["/app/deploy/common/run_cloud_job.sh"],
    }
    if args.registry_auth_id:
        payload["containerRegistryAuthId"] = args.registry_auth_id

    pod = request("POST", "/pods", token, payload)
    pod_id = pod["id"]
    print(pod_id)


if __name__ == "__main__":
    main()

```

## `infra/runpod/delete_job.py`

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pod_id")
    args = parser.parse_args()

    req = urllib.request.Request(
        f"https://rest.runpod.io/v1/pods/{args.pod_id}",
        headers={"Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}"},
        method="DELETE",
    )
    with urllib.request.urlopen(req) as resp:
        if resp.status != 204:
            raise SystemExit(f"Unexpected status: {resp.status}")


if __name__ == "__main__":
    main()

```

## `infra/vast/create_job.sh`

```bash
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

```

## `infra/vast/destroy_job.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
: "${VAST_API_KEY:?VAST_API_KEY is required}"
: "${1:?instance id is required}"

python -m pip install --quiet --upgrade vastai
vastai destroy instance "$1" --api-key "$VAST_API_KEY"

```

## `infra/hf/run_eval_job.sh`

```bash
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

```

## `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"

      - run: python -m pip install --upgrade pip
      - run: pip install -e . pytest

      - name: Compile
        run: python -m compileall src scripts infra

      - name: Test
        run: pytest -q

      - name: Validate shell scripts
        run: |
          bash -n deploy/common/mount_hf.sh
          bash -n deploy/common/run_cloud_job.sh
          bash -n infra/vast/create_job.sh
          bash -n infra/vast/destroy_job.sh
          bash -n infra/hf/run_eval_job.sh

```

## `.github/workflows/images.yml`

```yaml
name: Build GHCR Images

on:
  push:
    branches: [main]
    paths:
      - "docker/**"
      - "src/**"
      - "scripts/**"
      - "deploy/**"
      - "pyproject.toml"
      - ".github/workflows/images.yml"
  workflow_dispatch:

permissions:
  contents: read
  packages: write
  attestations: write
  id-token: write

concurrency:
  group: images-${{ github.ref }}
  cancel-in-progress: false

env:
  REGISTRY: ghcr.io

jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        include:
          - name: parakeet
            dockerfile: docker/parakeet/Dockerfile
          - name: stepaudio
            dockerfile: docker/stepaudio/Dockerfile
          - name: train
            dockerfile: docker/train/Dockerfile
          - name: eval
            dockerfile: docker/eval/Dockerfile

    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v6

      - uses: docker/setup-buildx-action@v3

      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: |
            ${{ env.REGISTRY }}/${{ github.repository_owner }}/audio-editorial-${{ matrix.name }}
          tags: |
            type=sha,prefix=sha-,format=long
            type=raw,value=main,enable={{is_default_branch}}
          labels: |
            org.opencontainers.image.revision=${{ github.sha }}
            org.opencontainers.image.source=${{ github.server_url }}/${{ github.repository }}

      - name: Build and push
        id: build
        uses: docker/build-push-action@v6
        with:
          context: .
          file: ${{ matrix.dockerfile }}
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha,scope=${{ matrix.name }}
          cache-to: type=gha,mode=max,scope=${{ matrix.name }}

      - name: Attest image provenance
        uses: actions/attest@v4
        with:
          subject-name: ${{ env.REGISTRY }}/${{ github.repository_owner }}/audio-editorial-${{ matrix.name }}
          subject-digest: ${{ steps.build.outputs.digest }}
          push-to-registry: true

```

## `.github/workflows/gpu-job.yml`

```yaml
name: GPU Job

on:
  workflow_dispatch:
    inputs:
      provider:
        description: GPU provider
        type: choice
        required: true
        options:
          - runpod
          - vast
      job_kind:
        description: Job to execute
        type: choice
        required: true
        options:
          - smoke
          - teacher
          - context-train
          - editorial-train
      image_kind:
        description: GHCR image family
        type: choice
        required: true
        options:
          - stepaudio
          - train
      image_tag:
        description: Immutable image tag; normally sha-<40-char-git-sha>
        required: true
      audio_rel:
        description: HF Bucket relative audio path for teacher
        required: false
        default: ""
      segments_rel:
        description: HF Bucket relative ASR segments path for teacher
        required: false
        default: ""
      train_rel:
        description: HF Bucket train.parquet relative path
        required: false
        default: ""
      valid_rel:
        description: HF Bucket validation.parquet relative path
        required: false
        default: ""
      epochs:
        description: Training epochs
        required: false
        default: "10"
      interruptible:
        description: Allow interruptible/spot capacity where supported
        type: boolean
        required: true
        default: false

permissions:
  contents: read
  packages: read

concurrency:
  group: gpu-${{ inputs.provider }}-${{ inputs.job_kind }}
  cancel-in-progress: false

jobs:
  launch:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    environment: gpu-${{ inputs.provider }}

    env:
      HF_TOKEN: ${{ secrets.HF_TOKEN }}
      HF_BUCKET: ${{ vars.HF_BUCKET }}
      HF_ROOT: /mnt/hf
      HF_HOME: /workspace/cache/huggingface
      NEMO_CACHE_DIR: /workspace/cache/nemo
      TORCH_HOME: /workspace/cache/torch

      RUNPOD_API_KEY: ${{ secrets.RUNPOD_API_KEY }}
      RUNPOD_REGISTRY_AUTH_ID: ${{ vars.RUNPOD_REGISTRY_AUTH_ID }}
      RUNPOD_CLOUD_TYPE: ${{ vars.RUNPOD_CLOUD_TYPE || 'SECURE' }}

      VAST_API_KEY: ${{ secrets.VAST_API_KEY }}
      VAST_GPU_QUERY: ${{ vars.VAST_GPU_QUERY || 'gpu_ram>=48000 num_gpus=1 reliability>0.98 verified=true rentable=true' }}
      VAST_DISK_GB: ${{ vars.VAST_DISK_GB || '150' }}

      JOB_KIND: ${{ inputs.job_kind }}
      RUN_ID: ${{ inputs.provider }}-${{ github.run_id }}-${{ github.run_attempt }}
      GIT_SHA: ${{ github.sha }}
      AUDIO_REL: ${{ inputs.audio_rel }}
      SEGMENTS_REL: ${{ inputs.segments_rel }}
      TRAIN_REL: ${{ inputs.train_rel }}
      VALID_REL: ${{ inputs.valid_rel }}
      EPOCHS: ${{ inputs.epochs }}

    steps:
      - uses: actions/checkout@v6

      - name: Compose immutable image reference
        run: |
          IMAGE_REF="ghcr.io/${GITHUB_REPOSITORY_OWNER}/audio-editorial-${{ inputs.image_kind }}:${{ inputs.image_tag }}"
          IMAGE_REF="${IMAGE_REF,,}"
          echo "IMAGE_REF=$IMAGE_REF" >> "$GITHUB_ENV"

      - name: Validate required inputs
        run: |
          case "$JOB_KIND" in
            teacher)
              test -n "$AUDIO_REL"
              test -n "$SEGMENTS_REL"
              ;;
            context-train|editorial-train)
              test -n "$TRAIN_REL"
              test -n "$VALID_REL"
              ;;
          esac

      - name: Launch Runpod
        if: inputs.provider == 'runpod'
        id: runpod
        env:
          INTERRUPTIBLE: ${{ inputs.interruptible }}
        run: |
          args=(
            --image "$IMAGE_REF"
            --name "audio-editorial-${JOB_KIND}-${RUN_ID}"
            --cloud-type "$RUNPOD_CLOUD_TYPE"
            --gpu "NVIDIA RTX A6000"
            --gpu "NVIDIA A40"
            --gpu "NVIDIA L40S"
          )

          if [ "$INTERRUPTIBLE" = "true" ]; then
            args+=(--interruptible)
          fi

          if [ -n "${RUNPOD_REGISTRY_AUTH_ID:-}" ]; then
            args+=(--registry-auth-id "$RUNPOD_REGISTRY_AUTH_ID")
          fi

          pod_id="$(python infra/runpod/create_job.py "${args[@]}")"
          echo "pod_id=$pod_id" >> "$GITHUB_OUTPUT"
          echo "Runpod pod: $pod_id"

      - name: Launch Vast
        if: inputs.provider == 'vast'
        id: vast
        run: |
          instance_id="$(bash infra/vast/create_job.sh)"
          echo "instance_id=$instance_id" >> "$GITHUB_OUTPUT"
          echo "Vast instance: $instance_id"

      - name: Write launch summary
        run: |
          {
            echo "## GPU Job launched"
            echo ""
            echo "- Provider: \`${{ inputs.provider }}\`"
            echo "- Job: \`${JOB_KIND}\`"
            echo "- Run ID: \`${RUN_ID}\`"
            echo "- Image: \`${IMAGE_REF}\`"
            echo "- HF result root: \`hf://buckets/${HF_BUCKET}/runs/${RUN_ID}/\`"
            if [ "${{ inputs.provider }}" = "runpod" ]; then
              echo "- Runpod Pod ID: \`${{ steps.runpod.outputs.pod_id }}\`"
            else
              echo "- Vast Instance ID: \`${{ steps.vast.outputs.instance_id }}\`"
            fi
          } >> "$GITHUB_STEP_SUMMARY"

```

## `.github/workflows/provider-cleanup.yml`

```yaml
name: Provider Cleanup

on:
  workflow_dispatch:
    inputs:
      provider:
        type: choice
        required: true
        options:
          - runpod
          - vast
      resource_id:
        description: Runpod Pod ID or Vast Instance ID
        required: true

permissions:
  contents: read

concurrency:
  group: cleanup-${{ inputs.provider }}-${{ inputs.resource_id }}
  cancel-in-progress: false

jobs:
  cleanup:
    runs-on: ubuntu-latest
    environment: gpu-${{ inputs.provider }}

    steps:
      - uses: actions/checkout@v6

      - name: Delete Runpod Pod
        if: inputs.provider == 'runpod'
        env:
          RUNPOD_API_KEY: ${{ secrets.RUNPOD_API_KEY }}
        run: python infra/runpod/delete_job.py "${{ inputs.resource_id }}"

      - name: Destroy Vast Instance
        if: inputs.provider == 'vast'
        env:
          VAST_API_KEY: ${{ secrets.VAST_API_KEY }}
        run: bash infra/vast/destroy_job.sh "${{ inputs.resource_id }}"

```

## `.github/workflows/hf-eval.yml`

```yaml
name: HF Golden Evaluation

on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: eval image tag, normally sha-<git-sha>
        required: true
      predictions_rel:
        description: HF Bucket relative predictions parquet
        required: true
      references_rel:
        description: HF Bucket relative golden/reference parquet
        required: true
        default: datasets/golden.parquet
      output_rel:
        description: HF Bucket relative output metrics JSON
        required: true

permissions:
  contents: read

concurrency:
  group: hf-eval-${{ inputs.predictions_rel }}
  cancel-in-progress: false

jobs:
  evaluate:
    runs-on: ubuntu-latest
    environment: hf-evaluation

    env:
      HF_TOKEN: ${{ secrets.HF_TOKEN }}
      HF_BUCKET: ${{ vars.HF_BUCKET }}
      PREDICTIONS_REL: ${{ inputs.predictions_rel }}
      REFERENCES_REL: ${{ inputs.references_rel }}
      OUTPUT_REL: ${{ inputs.output_rel }}

    steps:
      - uses: actions/checkout@v6

      - name: Build eval image reference
        run: |
          EVAL_IMAGE="ghcr.io/${GITHUB_REPOSITORY_OWNER}/audio-editorial-eval:${{ inputs.image_tag }}"
          EVAL_IMAGE="${EVAL_IMAGE,,}"
          echo "EVAL_IMAGE=$EVAL_IMAGE" >> "$GITHUB_ENV"

      - name: Run Hugging Face Job
        run: bash infra/hf/run_eval_job.sh

      - name: Summary
        run: |
          {
            echo "## HF evaluation submitted"
            echo "- Predictions: \`${PREDICTIONS_REL}\`"
            echo "- References: \`${REFERENCES_REL}\`"
            echo "- Output: \`hf://buckets/${HF_BUCKET}/${OUTPUT_REL}\`"
          } >> "$GITHUB_STEP_SUMMARY"

```

## `.github/workflows/provider-ablation.yml`

```yaml
name: Provider A/B Smoke

on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: Step-Audio image tag
        required: true

permissions:
  contents: read
  packages: read

jobs:
  runpod:
    uses: ./.github/workflows/reusable-provider-smoke.yml
    with:
      provider: runpod
      image_tag: ${{ inputs.image_tag }}
    secrets: inherit

  vast:
    uses: ./.github/workflows/reusable-provider-smoke.yml
    with:
      provider: vast
      image_tag: ${{ inputs.image_tag }}
    secrets: inherit

```

## `.github/workflows/reusable-provider-smoke.yml`

```yaml
name: Reusable Provider Smoke

on:
  workflow_call:
    inputs:
      provider:
        type: string
        required: true
      image_tag:
        type: string
        required: true

permissions:
  contents: read
  packages: read

jobs:
  launch:
    runs-on: ubuntu-latest
    environment: gpu-${{ inputs.provider }}

    env:
      HF_TOKEN: ${{ secrets.HF_TOKEN }}
      HF_BUCKET: ${{ vars.HF_BUCKET }}
      RUNPOD_API_KEY: ${{ secrets.RUNPOD_API_KEY }}
      RUNPOD_REGISTRY_AUTH_ID: ${{ vars.RUNPOD_REGISTRY_AUTH_ID }}
      VAST_API_KEY: ${{ secrets.VAST_API_KEY }}
      VAST_GPU_QUERY: ${{ vars.VAST_GPU_QUERY || 'gpu_ram>=48000 num_gpus=1 reliability>0.98 verified=true rentable=true' }}
      JOB_KIND: smoke
      RUN_ID: smoke-${{ inputs.provider }}-${{ github.run_id }}-${{ github.run_attempt }}
      GIT_SHA: ${{ github.sha }}

    steps:
      - uses: actions/checkout@v6

      - name: Image ref
        run: |
          IMAGE_REF="ghcr.io/${GITHUB_REPOSITORY_OWNER}/audio-editorial-stepaudio:${{ inputs.image_tag }}"
          IMAGE_REF="${IMAGE_REF,,}"
          echo "IMAGE_REF=$IMAGE_REF" >> "$GITHUB_ENV"

      - name: Runpod launch
        if: inputs.provider == 'runpod'
        run: |
          args=(
            --image "$IMAGE_REF"
            --name "$RUN_ID"
            --gpu "NVIDIA RTX A6000"
            --gpu "NVIDIA A40"
            --gpu "NVIDIA L40S"
          )
          if [ -n "${RUNPOD_REGISTRY_AUTH_ID:-}" ]; then
            args+=(--registry-auth-id "$RUNPOD_REGISTRY_AUTH_ID")
          fi
          python infra/runpod/create_job.py "${args[@]}"

      - name: Vast launch
        if: inputs.provider == 'vast'
        run: bash infra/vast/create_job.sh

      - name: Summary
        run: |
          echo "Smoke output will be written to hf://buckets/${HF_BUCKET}/runs/${RUN_ID}/" >> "$GITHUB_STEP_SUMMARY"

```

## `.github/workflows/release.yml`

```yaml
name: Release Gate

on:
  release:
    types: [published]
  workflow_dispatch:
    inputs:
      image_tag:
        description: Image tag to evaluate
        required: true
      predictions_rel:
        description: Candidate predictions in HF Bucket
        required: true
      references_rel:
        description: Golden references in HF Bucket
        required: true
        default: datasets/golden.parquet

permissions:
  contents: read

jobs:
  gate:
    runs-on: ubuntu-latest
    environment: release

    env:
      HF_TOKEN: ${{ secrets.HF_TOKEN }}
      HF_BUCKET: ${{ vars.HF_BUCKET }}

    steps:
      - uses: actions/checkout@v6

      - name: Resolve image tag
        run: |
          if [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
            echo "IMAGE_TAG=${{ inputs.image_tag }}" >> "$GITHUB_ENV"
            echo "PREDICTIONS_REL=${{ inputs.predictions_rel }}" >> "$GITHUB_ENV"
            echo "REFERENCES_REL=${{ inputs.references_rel }}" >> "$GITHUB_ENV"
          else
            echo "IMAGE_TAG=sha-${GITHUB_SHA}" >> "$GITHUB_ENV"
            echo "PREDICTIONS_REL=results/release/${GITHUB_SHA}/candidate.parquet" >> "$GITHUB_ENV"
            echo "REFERENCES_REL=datasets/golden.parquet" >> "$GITHUB_ENV"
          fi

      - name: Submit deterministic HF evaluation
        env:
          EVAL_IMAGE: ghcr.io/${{ github.repository_owner }}/audio-editorial-eval:${{ env.IMAGE_TAG }}
          OUTPUT_REL: results/release/${{ github.sha }}/metrics.json
        run: bash infra/hf/run_eval_job.sh

      - name: Release notes
        run: |
          echo "Release evaluation submitted to HF Jobs." >> "$GITHUB_STEP_SUMMARY"

```
