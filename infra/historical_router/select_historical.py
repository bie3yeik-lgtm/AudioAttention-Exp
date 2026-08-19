#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

import yaml

from history import load_cost_history
from predict import build_models, predict_runtime_hours_per_unit, predict_total_cost


def load_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def call_current_router(profile: str) -> dict:
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
        raise RuntimeError(p.stderr.strip())
    return json.loads(p.stdout)


def extract_candidates(router: dict) -> list[dict]:
    candidates = []

    vast = router.get("vast")
    if vast and vast.get("available"):
        candidates.append(
            {
                "provider": "vast",
                "gpu_id": vast.get("gpu_id", "unknown"),
                "offer_id": vast.get("offer_id"),
                "price_usd_per_hour": float(vast["price_usd_per_hour"]),
            }
        )

    runpod = router.get("runpod")
    if runpod and runpod.get("available"):
        candidates.append(
            {
                "provider": "runpod",
                "gpu_id": runpod.get("gpu_id", "unknown"),
                "price_usd_per_hour": float(runpod["price_usd_per_hour"]),
            }
        )

    return candidates


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workload", choices=["teacher", "student"], required=True)
    p.add_argument("--units", type=float, required=True)
    p.add_argument(
        "--bucket",
        default=os.environ.get("HF_BUCKET"),
    )
    p.add_argument(
        "--config",
        default="configs/historical-router.yaml",
    )
    args = p.parse_args()

    if not args.bucket:
        raise RuntimeError("HF_BUCKET or --bucket is required")
    if args.units <= 0:
        raise RuntimeError("--units must be > 0")

    cfg = load_yaml(args.config)
    hcfg = cfg["history"]
    pcfg = cfg["prediction"]
    objective = cfg["objectives"][args.workload]

    current = call_current_router(args.workload)
    candidates = extract_candidates(current)

    if not candidates:
        raise RuntimeError("Current Cost Router returned no usable candidates")

    rows = load_cost_history(
        args.bucket,
        max_records=int(hcfg["max_records"]),
        recency_days=int(hcfg["recency_days"]),
    )

    models = build_models(rows, workload=args.workload)

    predictions = []
    for candidate in candidates:
        runtime = predict_runtime_hours_per_unit(
            candidate=candidate,
            models=models,
            global_prior=float(objective["fallback_runtime_hours_per_unit"]),
            min_samples=int(hcfg["min_samples_per_candidate"]),
            prior_weight=float(pcfg["shrinkage_prior_weight"]),
            cold_start_multiplier=float(pcfg["cold_start_runtime_multiplier"]),
        )

        predictions.append(
            predict_total_cost(
                candidate=candidate,
                runtime_prediction=runtime,
                units=args.units,
                uncertainty_penalty=float(pcfg["uncertainty_penalty"]),
            )
        )

    predictions.sort(key=lambda x: x["risk_adjusted_total_cost_usd"])
    selected = predictions[0]

    result = {
        "workload": args.workload,
        "units": args.units,
        "unit_name": objective["unit"],
        "provider": selected["provider"],
        "gpu_id": selected["gpu_id"],
        "price_usd_per_hour": selected["price_usd_per_hour"],
        "predicted_runtime_hours": selected["predicted_runtime_hours"],
        "predicted_total_cost_usd": selected["predicted_total_cost_usd"],
        "risk_adjusted_total_cost_usd": selected["risk_adjusted_total_cost_usd"],
        "selected": selected,
        "candidates": predictions,
        "history_records_loaded": len(rows),
        "selection_reason": "minimum_predicted_risk_adjusted_total_cost",
    }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
