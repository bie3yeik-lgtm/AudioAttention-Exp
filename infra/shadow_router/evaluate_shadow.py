#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
from statistics import mean, median

from huggingface_hub import HfFileSystem


def load_json(fs, path):
    with fs.open(path, "r") as f:
        return json.load(f)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", required=True)
    p.add_argument("--job-id", required=True)
    p.add_argument("--historical-decision", required=True)
    args = p.parse_args()

    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))

    cost_path = f"hf://buckets/{args.bucket}/runs/{args.job_id}/cost.json"
    with open(args.historical_decision, "r", encoding="utf-8") as f:
        shadow = json.load(f)

    actual = load_json(fs, cost_path)

    actual_provider = actual["provider"]
    actual_gpu = actual.get("gpu_id") or actual.get("flavor") or "unknown"
    actual_cost = float(actual["estimated_cost_usd"])

    selected = shadow["selected"]
    shadow_provider = selected["provider"]
    shadow_gpu = selected.get("gpu_id") or selected.get("flavor") or "unknown"
    shadow_predicted_cost = float(selected["predicted_total_cost_usd"])

    same_route = (
        actual_provider == shadow_provider
        and str(actual_gpu) == str(shadow_gpu)
    )

    # Regret is defined from the perspective of the actual/current router:
    # positive => historical route predicted cheaper than what actually ran.
    predicted_regret_usd = actual_cost - shadow_predicted_cost

    prediction_error_ratio = (
        abs(shadow_predicted_cost - actual_cost) / actual_cost
        if same_route and actual_cost > 0
        else None
    )

    out = {
        "schema_version": "1.0",
        "job_id": args.job_id,
        "workload": actual["workload"],
        "actual": {
            "provider": actual_provider,
            "gpu_id": actual_gpu,
            "cost_usd": actual_cost
        },
        "shadow": {
            "provider": shadow_provider,
            "gpu_id": shadow_gpu,
            "predicted_cost_usd": shadow_predicted_cost,
            "risk_adjusted_cost_usd": selected["risk_adjusted_total_cost_usd"],
            "history_count": selected["history_count"],
            "source": selected["source"]
        },
        "same_route": same_route,
        "predicted_regret_usd": predicted_regret_usd,
        "relative_predicted_improvement": (
            predicted_regret_usd / actual_cost if actual_cost > 0 else None
        ),
        "same_route_prediction_error_ratio": prediction_error_ratio,
        "evaluable": True
    }

    out_path = f"hf://buckets/{args.bucket}/runs/{args.job_id}/routing-regret.json"
    with fs.open(out_path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
