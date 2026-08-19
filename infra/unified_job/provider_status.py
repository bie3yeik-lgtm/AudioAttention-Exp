from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import datetime, timezone
from typing import Any

from huggingface_hub import inspect_job


def runpod_status(resource_id: str) -> dict[str, Any]:
    req = urllib.request.Request(
        f"https://rest.runpod.io/v1/pods/{resource_id}",
        headers={
            "Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        obj = json.loads(resp.read())

    price = obj.get("adjustedCostPerHr")
    if price is None:
        price = obj.get("costPerHr")

    try:
        price = float(price)
    except (TypeError, ValueError):
        price = None

    return {
        "provider": "runpod",
        "resource_id": resource_id,
        "status": obj.get("desiredStatus"),
        "price_usd_per_hour": price,
        "raw": obj,
    }


def vast_status(resource_id: str) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "vastai",
            "show",
            "instance",
            str(resource_id),
            "--raw",
            "--api-key",
            os.environ["VAST_API_KEY"],
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)

    obj = json.loads(proc.stdout)
    if isinstance(obj, dict) and "instances" in obj:
        obj = obj["instances"]

    price = (
        obj.get("dph_total")
        or obj.get("dph_base")
        or obj.get("dph")
    )
    try:
        price = float(price)
    except (TypeError, ValueError):
        price = None

    return {
        "provider": "vast",
        "resource_id": resource_id,
        "status": obj.get("actual_status"),
        "price_usd_per_hour": price,
        "raw": obj,
    }


def hf_status(resource_id: str, namespace: str | None = None) -> dict[str, Any]:
    job = inspect_job(
        job_id=resource_id,
        namespace=namespace or None,
        token=os.environ.get("HF_TOKEN"),
    )

    stage = job.status.stage
    return {
        "provider": "hf_jobs",
        "resource_id": resource_id,
        "status": stage,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "flavor": job.flavor,
        "raw": {
            "id": job.id,
            "url": job.url,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        },
    }


def get_status(
    provider: str,
    resource_id: str,
    *,
    namespace: str | None = None,
) -> dict[str, Any]:
    if provider == "runpod":
        return runpod_status(resource_id)
    if provider == "vast":
        return vast_status(resource_id)
    if provider == "hf_jobs":
        return hf_status(resource_id, namespace=namespace)
    raise ValueError(f"Unsupported provider: {provider}")
