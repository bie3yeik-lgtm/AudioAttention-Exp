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
