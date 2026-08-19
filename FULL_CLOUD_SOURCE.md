# Full Cloud Source

## `configs/cost-router.yaml`

```yaml
version: 1

defaults:
  runpod_cloud_type: SECURE
  vast_disk_gb: 150
  runpod_container_disk_gb: 100
  runpod_volume_gb: 0
  price_tolerance_usd_per_hour: 0.01

profiles:
  teacher:
    image_kind: stepaudio

    vast:
      gpu_query: >-
        gpu_ram>=48000 num_gpus=1 reliability>0.98
        verified=true rentable=true
      max_dph: 0.40

    runpod:
      gpu_ids:
        - NVIDIA RTX A6000
        - NVIDIA A40
        - NVIDIA L40S
        - NVIDIA RTX 6000 Ada Generation
      max_dph: 0.55

  student:
    image_kind: train

    vast:
      gpu_query: >-
        gpu_ram>=24000 num_gpus=1 reliability>0.98
        verified=true rentable=true
      max_dph: 0.22

    runpod:
      gpu_ids:
        - NVIDIA RTX A5000
        - NVIDIA GeForce RTX 3090
        - NVIDIA GeForce RTX 4090
      max_dph: 0.35

```

## `infra/cost_router/select_provider.py`

```python
#!/usr/bin/env python3
"""
Cost-aware GPU provider selector.

Inputs:
  - configs/cost-router.yaml
  - VAST_API_KEY
  - RUNPOD_API_KEY

Outputs JSON to stdout:
{
  "provider": "vast" | "runpod",
  "profile": "teacher" | "student",
  "price_usd_per_hour": 0.31,
  ...
}

Selection policy:
1. Validate the workload profile.
2. Query Vast using:
     VAST_GPU_QUERY
     + disk_space >= VAST_DISK_GB
     + dph_total <= VAST_MAX_DPH
3. Query Runpod candidate GPU IDs using the official GraphQL API.
4. Reject unavailable or over-ceiling candidates.
5. Select the lowest-priced valid provider.
6. If prices differ by <= tolerance, prefer Runpod because it is the stable
   fallback provider; change PREFER_ON_TIE to "vast" if desired.

Notes:
- Vast dph_total includes the configured storage quantity used in the offer
  search.
- Runpod lowestPrice.uninterruptablePrice is the Pod GPU price returned by
  Runpod. This router intentionally configures Runpod volume_gb=0 by default,
  because HF Bucket is the persistent source of truth.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml


RUNPOD_GRAPHQL = "https://api.runpod.io/graphql"
PREFER_ON_TIE = "runpod"


class RouterError(RuntimeError):
    pass


def load_config(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def as_float(value: Any, name: str) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise RouterError(f"{name} must be numeric") from exc
    if value <= 0:
        raise RouterError(f"{name} must be > 0")
    return value


def run_vast_search(
    *,
    api_key: str,
    gpu_query: str,
    disk_gb: float,
    max_dph: float,
) -> dict[str, Any] | None:
    effective_query = (
        f"{gpu_query} "
        f"disk_space>={disk_gb:g} "
        f"dph_total<={max_dph:g}"
    )

    cmd = [
        "vastai",
        "search",
        "offers",
        effective_query,
        "--order=dph_total",
        "--storage",
        f"{disk_gb:g}",
        "--limit",
        "20",
        "--raw",
        "--api-key",
        api_key,
    ]

    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=False,
    )

    if proc.returncode != 0:
        return {
            "available": False,
            "error": "vast_search_failed",
            "detail": proc.stderr.strip(),
            "effective_query": effective_query,
        }

    try:
        offers = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {
            "available": False,
            "error": "vast_invalid_json",
            "detail": str(exc),
            "effective_query": effective_query,
        }

    if isinstance(offers, dict):
        offers = offers.get("offers", [])

    if not offers:
        return {
            "available": False,
            "error": "no_offer_under_ceiling",
            "effective_query": effective_query,
        }

    offer = offers[0]
    price = offer.get("dph_total")

    if price is None:
        return {
            "available": False,
            "error": "vast_offer_missing_dph_total",
            "effective_query": effective_query,
        }

    price = float(price)
    if price > max_dph + 1e-9:
        return {
            "available": False,
            "error": "vast_price_safety_check_failed",
            "effective_query": effective_query,
            "observed_price": price,
        }

    return {
        "available": True,
        "provider": "vast",
        "offer_id": str(offer["id"]),
        "gpu_id": str(offer.get("gpu_name", "unknown")),
        "gpu_ram_mb": offer.get("gpu_ram"),
        "price_usd_per_hour": price,
        "reliability": offer.get("reliability"),
        "disk_space_gb": offer.get("disk_space"),
        "effective_query": effective_query,
    }


def graphql(api_key: str, query: str) -> dict[str, Any]:
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        f"{RUNPOD_GRAPHQL}?api_key={api_key}",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RouterError(f"Runpod GraphQL request failed: {exc}") from exc

    if payload.get("errors"):
        raise RouterError(f"Runpod GraphQL error: {payload['errors']}")

    return payload["data"]


def escape_graphql(value: str) -> str:
    return json.dumps(value)


def query_runpod_gpu(
    *,
    api_key: str,
    gpu_id: str,
    cloud_type: str,
) -> dict[str, Any] | None:
    cloud_type = cloud_type.upper()

    if cloud_type == "SECURE":
        cloud_filter = ", secureCloud: true"
    elif cloud_type == "COMMUNITY":
        cloud_filter = ", secureCloud: false"
    elif cloud_type == "ALL":
        cloud_filter = ""
    else:
        raise RouterError(
            "runpod_cloud_type must be SECURE, COMMUNITY, or ALL"
        )

    query = f"""
    query {{
      gpuTypes(input: {{ id: {escape_graphql(gpu_id)} }}) {{
        id
        displayName
        memoryInGb
        secureCloud
        communityCloud
        lowestPrice(input: {{ gpuCount: 1{cloud_filter} }}) {{
          stockStatus
          uninterruptablePrice
          availableGpuCounts
        }}
      }}
    }}
    """

    data = graphql(api_key, query)
    items = data.get("gpuTypes") or []
    if not items:
        return None

    item = items[0]
    lowest = item.get("lowestPrice")
    if not lowest:
        return None

    price = lowest.get("uninterruptablePrice")
    stock = lowest.get("stockStatus")
    counts = lowest.get("availableGpuCounts") or []

    if price is None:
        return None

    # Runpod documents stockStatus values including High/Medium/Low/None.
    available = stock not in (None, "None") and 1 in counts

    return {
        "available": available,
        "provider": "runpod",
        "gpu_id": item["id"],
        "gpu_name": item.get("displayName"),
        "memory_gb": item.get("memoryInGb"),
        "price_usd_per_hour": float(price),
        "stock_status": stock,
        "available_gpu_counts": counts,
        "cloud_type": cloud_type,
    }


def best_runpod_candidate(
    *,
    api_key: str,
    gpu_ids: list[str],
    cloud_type: str,
    max_dph: float,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    inspected = []

    for gpu_id in gpu_ids:
        try:
            candidate = query_runpod_gpu(
                api_key=api_key,
                gpu_id=gpu_id,
                cloud_type=cloud_type,
            )
        except Exception as exc:
            inspected.append(
                {
                    "provider": "runpod",
                    "gpu_id": gpu_id,
                    "available": False,
                    "error": str(exc),
                }
            )
            continue

        if candidate is None:
            inspected.append(
                {
                    "provider": "runpod",
                    "gpu_id": gpu_id,
                    "available": False,
                    "error": "no_pricing_or_gpu_type",
                }
            )
            continue

        candidate["within_ceiling"] = (
            candidate["price_usd_per_hour"] <= max_dph + 1e-9
        )
        inspected.append(candidate)

    valid = [
        x
        for x in inspected
        if x.get("available")
        and x.get("within_ceiling")
        and "price_usd_per_hour" in x
    ]

    if not valid:
        return None, inspected

    valid.sort(key=lambda x: x["price_usd_per_hour"])
    return valid[0], inspected


def choose(
    *,
    vast: dict[str, Any] | None,
    runpod: dict[str, Any] | None,
    tolerance: float,
) -> tuple[dict[str, Any], str]:
    vast_ok = bool(vast and vast.get("available"))
    runpod_ok = bool(runpod and runpod.get("available"))

    if vast_ok and not runpod_ok:
        return vast, "only_vast_available"

    if runpod_ok and not vast_ok:
        return runpod, "only_runpod_available"

    if not vast_ok and not runpod_ok:
        raise RouterError(
            "No provider satisfies availability and price ceilings"
        )

    vast_price = float(vast["price_usd_per_hour"])
    runpod_price = float(runpod["price_usd_per_hour"])

    if abs(vast_price - runpod_price) <= tolerance:
        if PREFER_ON_TIE == "runpod":
            return runpod, "price_tie_prefer_runpod"
        return vast, "price_tie_prefer_vast"

    if vast_price < runpod_price:
        return vast, "vast_is_cheaper"

    return runpod, "runpod_is_cheaper"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["teacher", "student"], required=True)
    parser.add_argument(
        "--config",
        default="configs/cost-router.yaml",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    defaults = config["defaults"]
    profile = config["profiles"][args.profile]

    vast_api_key = os.environ["VAST_API_KEY"]
    runpod_api_key = os.environ["RUNPOD_API_KEY"]

    # Repository variables can override committed defaults.
    prefix = args.profile.upper()

    vast_gpu_query = os.environ.get(
        f"VAST_{prefix}_GPU_QUERY",
        profile["vast"]["gpu_query"],
    )
    vast_max_dph = as_float(
        os.environ.get(
            f"VAST_{prefix}_MAX_DPH",
            profile["vast"]["max_dph"],
        ),
        f"VAST_{prefix}_MAX_DPH",
    )

    runpod_gpu_ids_raw = os.environ.get(
        f"RUNPOD_{prefix}_GPU_IDS",
        "",
    )
    runpod_gpu_ids = (
        [x.strip() for x in runpod_gpu_ids_raw.split(",") if x.strip()]
        if runpod_gpu_ids_raw
        else list(profile["runpod"]["gpu_ids"])
    )

    runpod_max_dph = as_float(
        os.environ.get(
            f"RUNPOD_{prefix}_MAX_DPH",
            profile["runpod"]["max_dph"],
        ),
        f"RUNPOD_{prefix}_MAX_DPH",
    )

    vast_disk_gb = as_float(
        os.environ.get(
            f"VAST_{prefix}_DISK_GB",
            defaults["vast_disk_gb"],
        ),
        f"VAST_{prefix}_DISK_GB",
    )

    cloud_type = os.environ.get(
        "RUNPOD_CLOUD_TYPE",
        defaults["runpod_cloud_type"],
    )

    tolerance = float(
        os.environ.get(
            "COST_ROUTER_PRICE_TOLERANCE",
            defaults["price_tolerance_usd_per_hour"],
        )
    )

    vast = run_vast_search(
        api_key=vast_api_key,
        gpu_query=vast_gpu_query,
        disk_gb=vast_disk_gb,
        max_dph=vast_max_dph,
    )

    runpod, runpod_inspected = best_runpod_candidate(
        api_key=runpod_api_key,
        gpu_ids=runpod_gpu_ids,
        cloud_type=cloud_type,
        max_dph=runpod_max_dph,
    )

    selected, reason = choose(
        vast=vast,
        runpod=runpod,
        tolerance=tolerance,
    )

    output = {
        "profile": args.profile,
        "provider": selected["provider"],
        "reason": reason,
        "price_usd_per_hour": selected["price_usd_per_hour"],
        "selected": selected,
        "vast": vast,
        "runpod": runpod,
        "runpod_inspected": runpod_inspected,
        "ceilings": {
            "vast_max_dph": vast_max_dph,
            "runpod_max_dph": runpod_max_dph,
        },
    }

    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        raise

```

## `infra/cost_router/requirements.txt`

```text
PyYAML>=6.0,<7

```

## `.github/workflows/reusable-cost-router.yml`

```yaml
name: Reusable Cost Router

on:
  workflow_call:
    inputs:
      profile:
        description: teacher or student
        type: string
        required: true
    outputs:
      provider:
        description: Selected GPU provider
        value: ${{ jobs.route.outputs.provider }}
      gpu_id:
        description: Selected GPU/offer identifier
        value: ${{ jobs.route.outputs.gpu_id }}
      price:
        description: Selected USD/hour
        value: ${{ jobs.route.outputs.price }}
      vast_offer_id:
        description: Vast offer ID when Vast is selected
        value: ${{ jobs.route.outputs.vast_offer_id }}
      reason:
        description: Router decision reason
        value: ${{ jobs.route.outputs.reason }}
    secrets:
      VAST_API_KEY:
        required: true
      RUNPOD_API_KEY:
        required: true

permissions:
  contents: read

jobs:
  route:
    runs-on: ubuntu-latest

    outputs:
      provider: ${{ steps.route.outputs.provider }}
      gpu_id: ${{ steps.route.outputs.gpu_id }}
      price: ${{ steps.route.outputs.price }}
      vast_offer_id: ${{ steps.route.outputs.vast_offer_id }}
      reason: ${{ steps.route.outputs.reason }}

    env:
      VAST_API_KEY: ${{ secrets.VAST_API_KEY }}
      RUNPOD_API_KEY: ${{ secrets.RUNPOD_API_KEY }}

      # Workload-specific repository variables.
      VAST_TEACHER_GPU_QUERY: ${{ vars.VAST_TEACHER_GPU_QUERY }}
      VAST_TEACHER_MAX_DPH: ${{ vars.VAST_TEACHER_MAX_DPH }}
      VAST_TEACHER_DISK_GB: ${{ vars.VAST_TEACHER_DISK_GB }}

      VAST_STUDENT_GPU_QUERY: ${{ vars.VAST_STUDENT_GPU_QUERY }}
      VAST_STUDENT_MAX_DPH: ${{ vars.VAST_STUDENT_MAX_DPH }}
      VAST_STUDENT_DISK_GB: ${{ vars.VAST_STUDENT_DISK_GB }}

      RUNPOD_TEACHER_GPU_IDS: ${{ vars.RUNPOD_TEACHER_GPU_IDS }}
      RUNPOD_TEACHER_MAX_DPH: ${{ vars.RUNPOD_TEACHER_MAX_DPH }}

      RUNPOD_STUDENT_GPU_IDS: ${{ vars.RUNPOD_STUDENT_GPU_IDS }}
      RUNPOD_STUDENT_MAX_DPH: ${{ vars.RUNPOD_STUDENT_MAX_DPH }}

      RUNPOD_CLOUD_TYPE: ${{ vars.RUNPOD_CLOUD_TYPE }}
      COST_ROUTER_PRICE_TOLERANCE: ${{ vars.COST_ROUTER_PRICE_TOLERANCE }}

    steps:
      - uses: actions/checkout@v6

      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"

      - name: Install router dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r infra/cost_router/requirements.txt
          pip install --upgrade vastai

      - name: Select cheapest valid provider
        id: route
        shell: bash
        run: |
          result="$(
            python infra/cost_router/select_provider.py \
              --profile '${{ inputs.profile }}'
          )"

          echo "$result" | python -m json.tool

          provider="$(echo "$result" | jq -r '.provider')"
          price="$(echo "$result" | jq -r '.price_usd_per_hour')"
          reason="$(echo "$result" | jq -r '.reason')"
          gpu_id="$(echo "$result" | jq -r '.selected.gpu_id // empty')"
          vast_offer_id="$(echo "$result" | jq -r '.selected.offer_id // empty')"

          echo "provider=$provider" >> "$GITHUB_OUTPUT"
          echo "price=$price" >> "$GITHUB_OUTPUT"
          echo "reason=$reason" >> "$GITHUB_OUTPUT"
          echo "gpu_id=$gpu_id" >> "$GITHUB_OUTPUT"
          echo "vast_offer_id=$vast_offer_id" >> "$GITHUB_OUTPUT"

          {
            echo "## Cost Router"
            echo ""
            echo "- Profile: \`${{ inputs.profile }}\`"
            echo "- Provider: \`$provider\`"
            echo "- GPU: \`$gpu_id\`"
            echo "- Price: \`$price USD/h\`"
            echo "- Reason: \`$reason\`"
            echo ""
            echo "<details><summary>Full routing decision</summary>"
            echo ""
            echo '```json'
            echo "$result" | jq .
            echo '```'
            echo "</details>"
          } >> "$GITHUB_STEP_SUMMARY"

```

## `.github/workflows/teacher-job.yml`

```yaml
name: Teacher GPU Job

on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: Immutable Step-Audio GHCR tag
        required: true
      audio_rel:
        description: HF Bucket relative audio path
        required: true
      segments_rel:
        description: HF Bucket relative Parakeet segments path
        required: true

permissions:
  contents: read
  packages: read

concurrency:
  group: teacher-gpu
  cancel-in-progress: false

jobs:
  route:
    uses: ./.github/workflows/reusable-cost-router.yml
    with:
      profile: teacher
    secrets:
      VAST_API_KEY: ${{ secrets.VAST_API_KEY }}
      RUNPOD_API_KEY: ${{ secrets.RUNPOD_API_KEY }}

  launch:
    needs: route
    runs-on: ubuntu-latest
    environment: gpu-auto

    env:
      HF_TOKEN: ${{ secrets.HF_TOKEN }}
      HF_BUCKET: ${{ vars.HF_BUCKET }}
      VAST_API_KEY: ${{ secrets.VAST_API_KEY }}
      RUNPOD_API_KEY: ${{ secrets.RUNPOD_API_KEY }}
      RUNPOD_REGISTRY_AUTH_ID: ${{ vars.RUNPOD_REGISTRY_AUTH_ID }}
      RUNPOD_CLOUD_TYPE: ${{ vars.RUNPOD_CLOUD_TYPE || 'SECURE' }}

      JOB_KIND: teacher
      RUN_ID: teacher-${{ github.run_id }}-${{ github.run_attempt }}
      GIT_SHA: ${{ github.sha }}

      AUDIO_REL: ${{ inputs.audio_rel }}
      SEGMENTS_REL: ${{ inputs.segments_rel }}

    steps:
      - uses: actions/checkout@v6

      - name: Build image reference
        shell: bash
        run: |
          IMAGE_REF="ghcr.io/${GITHUB_REPOSITORY_OWNER}/audio-editorial-stepaudio:${{ inputs.image_tag }}"
          echo "IMAGE_REF=${IMAGE_REF,,}" >> "$GITHUB_ENV"

      - name: Launch Vast
        if: needs.route.outputs.provider == 'vast'
        shell: bash
        env:
          VAST_OFFER_ID: ${{ needs.route.outputs.vast_offer_id }}
          VAST_DISK_GB: ${{ vars.VAST_TEACHER_DISK_GB || '150' }}
        run: |
          instance_id="$(bash infra/vast/create_job.sh)"
          echo "Vast instance: $instance_id" >> "$GITHUB_STEP_SUMMARY"

      - name: Launch Runpod
        if: needs.route.outputs.provider == 'runpod'
        shell: bash
        env:
          RUNPOD_GPU_ID: ${{ needs.route.outputs.gpu_id }}
        run: |
          args=(
            --image "$IMAGE_REF"
            --name "$RUN_ID"
            --cloud-type "$RUNPOD_CLOUD_TYPE"
            --gpu "$RUNPOD_GPU_ID"
            --container-disk 100
            --volume 0
          )

          if [ -n "${RUNPOD_REGISTRY_AUTH_ID:-}" ]; then
            args+=(--registry-auth-id "$RUNPOD_REGISTRY_AUTH_ID")
          fi

          pod_id="$(python infra/runpod/create_job.py "${args[@]}")"
          echo "Runpod pod: $pod_id" >> "$GITHUB_STEP_SUMMARY"

      - name: Cost summary
        run: |
          {
            echo "## Teacher launch"
            echo "- Provider: \`${{ needs.route.outputs.provider }}\`"
            echo "- GPU: \`${{ needs.route.outputs.gpu_id }}\`"
            echo "- Estimated compute price: \`${{ needs.route.outputs.price }} USD/h\`"
            echo "- Router reason: \`${{ needs.route.outputs.reason }}\`"
            echo "- HF run path: \`hf://buckets/$HF_BUCKET/runs/$RUN_ID/\`"
          } >> "$GITHUB_STEP_SUMMARY"

```

## `.github/workflows/student-job.yml`

```yaml
name: Student GPU Job

on:
  workflow_dispatch:
    inputs:
      model:
        description: Student model
        type: choice
        required: true
        options:
          - context
          - editorial
      image_tag:
        description: Immutable train GHCR tag
        required: true
      train_rel:
        description: HF Bucket relative training parquet
        required: true
      valid_rel:
        description: HF Bucket relative validation parquet
        required: true
      epochs:
        description: Epochs
        required: true
        default: "10"

permissions:
  contents: read
  packages: read

concurrency:
  group: student-${{ inputs.model }}
  cancel-in-progress: false

jobs:
  route:
    uses: ./.github/workflows/reusable-cost-router.yml
    with:
      profile: student
    secrets:
      VAST_API_KEY: ${{ secrets.VAST_API_KEY }}
      RUNPOD_API_KEY: ${{ secrets.RUNPOD_API_KEY }}

  launch:
    needs: route
    runs-on: ubuntu-latest
    environment: gpu-auto

    env:
      HF_TOKEN: ${{ secrets.HF_TOKEN }}
      HF_BUCKET: ${{ vars.HF_BUCKET }}
      VAST_API_KEY: ${{ secrets.VAST_API_KEY }}
      RUNPOD_API_KEY: ${{ secrets.RUNPOD_API_KEY }}
      RUNPOD_REGISTRY_AUTH_ID: ${{ vars.RUNPOD_REGISTRY_AUTH_ID }}
      RUNPOD_CLOUD_TYPE: ${{ vars.RUNPOD_CLOUD_TYPE || 'COMMUNITY' }}

      JOB_KIND: ${{ inputs.model == 'context' && 'context-train' || 'editorial-train' }}
      RUN_ID: student-${{ inputs.model }}-${{ github.run_id }}-${{ github.run_attempt }}
      GIT_SHA: ${{ github.sha }}

      TRAIN_REL: ${{ inputs.train_rel }}
      VALID_REL: ${{ inputs.valid_rel }}
      EPOCHS: ${{ inputs.epochs }}

    steps:
      - uses: actions/checkout@v6

      - name: Build image reference
        shell: bash
        run: |
          IMAGE_REF="ghcr.io/${GITHUB_REPOSITORY_OWNER}/audio-editorial-train:${{ inputs.image_tag }}"
          echo "IMAGE_REF=${IMAGE_REF,,}" >> "$GITHUB_ENV"

      - name: Launch Vast
        if: needs.route.outputs.provider == 'vast'
        shell: bash
        env:
          VAST_OFFER_ID: ${{ needs.route.outputs.vast_offer_id }}
          VAST_DISK_GB: ${{ vars.VAST_STUDENT_DISK_GB || '100' }}
        run: |
          instance_id="$(bash infra/vast/create_job.sh)"
          echo "Vast instance: $instance_id" >> "$GITHUB_STEP_SUMMARY"

      - name: Launch Runpod
        if: needs.route.outputs.provider == 'runpod'
        shell: bash
        env:
          RUNPOD_GPU_ID: ${{ needs.route.outputs.gpu_id }}
        run: |
          args=(
            --image "$IMAGE_REF"
            --name "$RUN_ID"
            --cloud-type "$RUNPOD_CLOUD_TYPE"
            --gpu "$RUNPOD_GPU_ID"
            --container-disk 80
            --volume 0
          )

          if [ -n "${RUNPOD_REGISTRY_AUTH_ID:-}" ]; then
            args+=(--registry-auth-id "$RUNPOD_REGISTRY_AUTH_ID")
          fi

          pod_id="$(python infra/runpod/create_job.py "${args[@]}")"
          echo "Runpod pod: $pod_id" >> "$GITHUB_STEP_SUMMARY"

      - name: Cost summary
        run: |
          {
            echo "## Student launch"
            echo "- Model: \`${{ inputs.model }}\`"
            echo "- Provider: \`${{ needs.route.outputs.provider }}\`"
            echo "- GPU: \`${{ needs.route.outputs.gpu_id }}\`"
            echo "- Estimated compute price: \`${{ needs.route.outputs.price }} USD/h\`"
            echo "- Router reason: \`${{ needs.route.outputs.reason }}\`"
            echo "- HF run path: \`hf://buckets/$HF_BUCKET/runs/$RUN_ID/\`"
          } >> "$GITHUB_STEP_SUMMARY"

```

## `docs/teacher-student-cost-router.md`

```markdown
# Teacher / Student Cost Router

## Goal

Select the cheapest currently usable GPU provider independently for the two
workloads.

```text
Teacher
  Step-Audio-2-mini
  >=48 GB VRAM
  tighter reliability requirements

Student
  Context / Editorial training
  >=24 GB VRAM
  cheap marketplace/consumer GPU acceptable
```

## Repository variables

Recommended initial values:

```text
# Vast: Teacher
VAST_TEACHER_GPU_QUERY=gpu_ram>=48000 num_gpus=1 reliability>0.98 verified=true rentable=true
VAST_TEACHER_DISK_GB=150
VAST_TEACHER_MAX_DPH=0.40

# Vast: Student
VAST_STUDENT_GPU_QUERY=gpu_ram>=24000 num_gpus=1 reliability>0.98 verified=true rentable=true
VAST_STUDENT_DISK_GB=100
VAST_STUDENT_MAX_DPH=0.22

# Runpod: Teacher
RUNPOD_TEACHER_GPU_IDS=NVIDIA RTX A6000,NVIDIA A40,NVIDIA L40S,NVIDIA RTX 6000 Ada Generation
RUNPOD_TEACHER_MAX_DPH=0.55

# Runpod: Student
RUNPOD_STUDENT_GPU_IDS=NVIDIA RTX A5000,NVIDIA GeForce RTX 3090,NVIDIA GeForce RTX 4090
RUNPOD_STUDENT_MAX_DPH=0.35

# Shared
RUNPOD_CLOUD_TYPE=SECURE
COST_ROUTER_PRICE_TOLERANCE=0.01
```

The committed `configs/cost-router.yaml` values are defaults. GitHub repository
variables override them.

## Secrets

```text
VAST_API_KEY
RUNPOD_API_KEY
HF_TOKEN
```

## Selection algorithm

```text
                 workload profile
                  /            \
             teacher          student
                |                |
                v                v
          Vast 48GB+        Vast 24GB+
          own ceiling       own ceiling
                |                |
                +-------+--------+
                        |
                        v
                 Vast best offer
                        |
              +---------+---------+
              |                   |
              v                   v
       Runpod candidate 1   Runpod candidate N
              |                   |
              +---------+---------+
                        |
                        v
              cheapest valid Runpod
                        |
                        v
                 compare USD/hour
                        |
             +----------+----------+
             |                     |
            Vast                 Runpod
```

A provider is valid only if it is available and does not exceed its own price
ceiling.

If the difference between the two cheapest providers is within
`COST_ROUTER_PRICE_TOLERANCE`, Runpod is preferred by default because it is the
stable fallback service. This can be changed in `select_provider.py`.

## Why Runpod volume is zero

HF Storage Bucket is the persistent source of truth. The cost router therefore
uses Runpod local/container storage as disposable cache and defaults persistent
Runpod volume to zero. This also makes the hourly GPU comparison more meaningful.

## Workflows

- `teacher-job.yml`
  - calls `reusable-cost-router.yml` with `profile=teacher`
  - starts Step-Audio Teacher on the selected provider.

- `student-job.yml`
  - calls the router with `profile=student`
  - starts Context or Editorial training.

- `reusable-cost-router.yml`
  - queries Vast and Runpod
  - returns provider/GPU/price as workflow outputs.

## Failure policy

Routing failure:

```text
No Vast offer <= Vast ceiling
AND
No Runpod GPU <= Runpod ceiling
    ->
fail closed
```

Do not silently start an over-ceiling GPU.

Instance-creation race should be handled as a second layer:
if the selected Vast offer disappears before creation, rerun the router or
fall back to the already-inspected Runpod candidate.

```
