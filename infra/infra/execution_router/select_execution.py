#!/usr/bin/env python3
"""
Top-level execution router.

It decides between:
- Hugging Face Jobs
- Vast
- Runpod

The lower-level Vast/Runpod GPU comparison remains in
infra/cost_router/select_provider.py.

Policy:
- CPU preprocessing/validation/golden metrics -> HF Jobs.
- Teacher GPU -> Vast/Runpod cost router.
- Student GPU -> Vast/Runpod cost router.
- Golden GPU -> compare best Vast/Runpod candidate against a fixed,
  reproducible HF Jobs GPU flavor and select the cheapest candidate
  under all configured ceilings.

HF Jobs hardware/pricing is queried dynamically with `hf jobs hardware --json`
when available. A fallback parser handles current text output so repository
configuration does not need to embed live prices.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


class ExecutionRouterError(RuntimeError):
    pass


def load_yaml(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_json(cmd: list[str]) -> Any:
    p = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if p.returncode != 0:
        raise ExecutionRouterError(
            f"Command failed ({p.returncode}): {' '.join(cmd)}\n{p.stderr}"
        )
    return json.loads(p.stdout)


def get_hf_hardware() -> list[dict[str, Any]]:
    # Prefer a hypothetical/current JSON output when supported.
    p = subprocess.run(
        ["hf", "jobs", "hardware", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    if p.returncode == 0:
        try:
            obj = json.loads(p.stdout)
            if isinstance(obj, dict):
                for key in ("hardware", "items", "data"):
                    if isinstance(obj.get(key), list):
                        return obj[key]
            if isinstance(obj, list):
                return obj
        except json.JSONDecodeError:
            pass

    # Official REST endpoint fallback.
    import urllib.request

    req = urllib.request.Request(
        "https://huggingface.co/api/jobs/hardware",
        headers={
            "Authorization": f"Bearer {os.environ['HF_TOKEN']}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            obj = json.loads(resp.read())
    except Exception as exc:
        raise ExecutionRouterError(
            f"Could not retrieve HF Jobs hardware pricing: {exc}"
        ) from exc

    if isinstance(obj, dict):
        for key in ("hardware", "items", "data"):
            if isinstance(obj.get(key), list):
                return obj[key]

    if isinstance(obj, list):
        return obj

    raise ExecutionRouterError(
        f"Unexpected HF hardware response: {type(obj).__name__}"
    )


def normalize_hf_item(item: dict[str, Any]) -> dict[str, Any]:
    name = (
        item.get("name")
        or item.get("flavor")
        or item.get("id")
        or item.get("slug")
    )

    cost_hour = (
        item.get("cost_hour")
        or item.get("costPerHour")
        or item.get("cost_per_hour")
        or item.get("hourlyPrice")
        or item.get("price")
    )

    if isinstance(cost_hour, str):
        cost_hour = cost_hour.replace("$", "").strip()

    try:
        cost_hour = float(cost_hour)
    except (TypeError, ValueError):
        cost_hour = None

    return {
        "provider": "hf_jobs",
        "flavor": name,
        "price_usd_per_hour": cost_hour,
        "raw": item,
    }


def hf_candidate(
    *,
    flavor: str,
    max_dph: float,
) -> dict[str, Any] | None:
    hardware = [normalize_hf_item(x) for x in get_hf_hardware()]

    matches = [x for x in hardware if x["flavor"] == flavor]
    if not matches:
        return None

    item = matches[0]
    price = item["price_usd_per_hour"]

    if price is None:
        return None

    item["available"] = True
    item["within_ceiling"] = price <= max_dph + 1e-9
    return item


def call_gpu_router(profile: str) -> dict[str, Any]:
    p = subprocess.run(
        [
            sys.executable,
            "infra/cost_router/select_provider.py",
            "--profile",
            profile,
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    if p.returncode != 0:
        try:
            err = json.loads(p.stderr.strip().splitlines()[-1])
        except Exception:
            err = {"message": p.stderr.strip()}
        return {
            "available": False,
            "provider": "gpu-router",
            "error": err,
        }

    obj = json.loads(p.stdout)
    obj["available"] = True
    return obj


def choose_cheapest(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [
        x for x in candidates
        if x.get("available")
        and x.get("within_ceiling", True)
        and x.get("price_usd_per_hour") is not None
    ]

    if not valid:
        raise ExecutionRouterError(
            "No execution provider satisfies availability and price ceilings"
        )

    valid.sort(key=lambda x: float(x["price_usd_per_hour"]))
    return valid[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workload",
        choices=[
            "preprocess",
            "validate",
            "golden-cpu",
            "teacher",
            "student",
            "golden-gpu",
        ],
        required=True,
    )
    parser.add_argument(
        "--config",
        default="configs/execution-router.yaml",
    )
    args = parser.parse_args()

    cfg = load_yaml(args.config)
    workload = cfg["workloads"][args.workload]
    defaults = cfg["defaults"]

    providers = workload["providers"]

    if workload["class"] == "cpu":
        if providers != ["hf_jobs"]:
            raise ExecutionRouterError(
                "CPU workloads are expected to use HF Jobs only"
            )

        flavor = os.environ.get(
            "HF_CPU_FLAVOR",
            defaults["hf_cpu_flavor"],
        )
        max_dph = float(
            os.environ.get(
                "HF_CPU_MAX_DPH",
                defaults["hf_cpu_max_dph"],
            )
        )

        candidate = hf_candidate(
            flavor=flavor,
            max_dph=max_dph,
        )

        if not candidate or not candidate["within_ceiling"]:
            raise ExecutionRouterError(
                f"HF CPU flavor {flavor} is unavailable or exceeds ceiling"
            )

        result = {
            "workload": args.workload,
            "class": "cpu",
            "provider": "hf_jobs",
            "price_usd_per_hour": candidate["price_usd_per_hour"],
            "selected": candidate,
            "reason": "cpu_workload_hf_jobs",
        }

        print(json.dumps(result, ensure_ascii=False))
        return

    gpu_result = call_gpu_router(workload["cost_profile"])

    if args.workload != "golden-gpu":
        if not gpu_result.get("available"):
            raise ExecutionRouterError(
                f"GPU router found no valid provider: {gpu_result}"
            )

        result = {
            "workload": args.workload,
            "class": "gpu",
            "provider": gpu_result["provider"],
            "price_usd_per_hour": gpu_result["price_usd_per_hour"],
            "selected": gpu_result["selected"],
            "reason": f"{args.workload}_vast_runpod_cost_router",
            "gpu_router": gpu_result,
        }

        print(json.dumps(result, ensure_ascii=False))
        return

    hf_flavor = os.environ.get(
        "HF_GOLDEN_GPU_FLAVOR",
        defaults["hf_gpu_golden_flavor"],
    )
    hf_max_dph = float(
        os.environ.get(
            "HF_GOLDEN_GPU_MAX_DPH",
            defaults["hf_gpu_golden_max_dph"],
        )
    )

    hf = hf_candidate(
        flavor=hf_flavor,
        max_dph=hf_max_dph,
    )

    candidates: list[dict[str, Any]] = []

    if gpu_result.get("available"):
        candidates.append({
            "available": True,
            "provider": gpu_result["provider"],
            "price_usd_per_hour": gpu_result["price_usd_per_hour"],
            "selected": gpu_result["selected"],
            "source": "vast_runpod_cost_router",
        })

    if hf:
        candidates.append(hf)

    selected = choose_cheapest(candidates)

    result = {
        "workload": args.workload,
        "class": "gpu",
        "provider": selected["provider"],
        "price_usd_per_hour": selected["price_usd_per_hour"],
        "selected": selected,
        "reason": "golden_gpu_cheapest_valid_provider",
        "gpu_router": gpu_result,
        "hf_jobs": hf,
    }

    print(json.dumps(result, ensure_ascii=False))


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
