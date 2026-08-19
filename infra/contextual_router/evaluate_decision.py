#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os

from huggingface_hub import HfFileSystem


def ident(provider: str, gpu_id: str | None) -> str:
    return f"{provider}::{gpu_id or 'unknown'}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", required=True)
    p.add_argument("--job-id", required=True)
    args = p.parse_args()

    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))

    decision_path = (
        f"hf://buckets/{args.bucket}/runs/"
        f"{args.job_id}/contextual-decision.json"
    )
    cost_path = (
        f"hf://buckets/{args.bucket}/runs/"
        f"{args.job_id}/cost.json"
    )

    with fs.open(decision_path, "r") as f:
        decision = json.load(f)

    with fs.open(cost_path, "r") as f:
        actual = json.load(f)

    actual_provider = actual["provider"]
    actual_gpu = actual.get("gpu_id") or actual.get("flavor") or "unknown"
    actual_cost = float(actual["estimated_cost_usd"])
    actual_runtime = float(actual["runtime_seconds"])

    historical = decision["historical_greedy"]
    contextual = decision["contextual_recommendation"]

    historical_same_route = (
        ident(actual_provider, actual_gpu)
        == ident(historical["provider"], historical.get("gpu_id"))
    )
    contextual_same_route = (
        ident(actual_provider, actual_gpu)
        == ident(contextual["provider"], contextual.get("gpu_id"))
    )

    # Historical prediction fields come from Historical Router.
    historical_pred_cost = float(
        historical.get(
            "predicted_total_cost_usd",
            historical.get("risk_adjusted_total_cost_usd", 0.0),
        )
    )
    historical_pred_runtime_seconds = (
        float(historical.get("predicted_runtime_hours", 0.0)) * 3600.0
    )

    contextual_pred_cost = float(
        contextual["contextual_blended_total_cost_usd"]
    )
    contextual_pred_runtime_seconds = float(
        contextual["predicted_runtime_seconds"]
    )

    def abs_error(pred: float, actual_value: float) -> float:
        return abs(pred - actual_value)

    def ape(pred: float, actual_value: float) -> float | None:
        if actual_value <= 0:
            return None
        return abs(pred - actual_value) / actual_value

    out = {
        "schema_version": "1.0",
        "job_id": args.job_id,
        "workload": actual["workload"],
        "actual": {
            "provider": actual_provider,
            "gpu_id": actual_gpu,
            "cost_usd": actual_cost,
            "runtime_seconds": actual_runtime,
        },
        "historical": {
            "provider": historical["provider"],
            "gpu_id": historical.get("gpu_id"),
            "predicted_cost_usd": historical_pred_cost,
            "predicted_runtime_seconds": historical_pred_runtime_seconds,
            "same_route": historical_same_route,
            "cost_absolute_error_usd": (
                abs_error(historical_pred_cost, actual_cost)
                if historical_same_route else None
            ),
            "cost_ape": (
                ape(historical_pred_cost, actual_cost)
                if historical_same_route else None
            ),
            "runtime_ape": (
                ape(historical_pred_runtime_seconds, actual_runtime)
                if historical_same_route else None
            ),
        },
        "contextual": {
            "provider": contextual["provider"],
            "gpu_id": contextual.get("gpu_id"),
            "model_version": decision.get("model_version"),
            "predicted_cost_usd": contextual_pred_cost,
            "predicted_runtime_seconds": contextual_pred_runtime_seconds,
            "same_route": contextual_same_route,
            "cost_absolute_error_usd": (
                abs_error(contextual_pred_cost, actual_cost)
                if contextual_same_route else None
            ),
            "cost_ape": (
                ape(contextual_pred_cost, actual_cost)
                if contextual_same_route else None
            ),
            "runtime_ape": (
                ape(contextual_pred_runtime_seconds, actual_runtime)
                if contextual_same_route else None
            ),
        },
        # Direct model-vs-model error improvement is only observable when both
        # recommend the actually executed route.
        "both_same_route": historical_same_route and contextual_same_route,
        "contextual_minus_historical_abs_cost_error_usd": (
            abs_error(contextual_pred_cost, actual_cost)
            - abs_error(historical_pred_cost, actual_cost)
            if historical_same_route and contextual_same_route else None
        ),
        "evaluable": True,
    }

    out_path = (
        f"hf://buckets/{args.bucket}/runs/"
        f"{args.job_id}/contextual-evaluation.json"
    )
    with fs.open(out_path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
