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
