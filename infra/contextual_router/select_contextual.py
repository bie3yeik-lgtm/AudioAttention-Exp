#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any

from features import candidate_feature_row
from model import ContextualModel


def call_historical(workload: str, units: float) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = "infra/historical_router"

    p = subprocess.run(
        [
            sys.executable,
            "infra/historical_router/select_historical.py",
            "--workload",
            workload,
            "--units",
            str(units),
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip())

    return json.loads(p.stdout)


def infer_accounting(workload: str, units: float) -> dict[str, Any]:
    if workload == "teacher":
        return {
            "input_audio_hours": units,
            "epochs": None,
            "samples": None,
        }

    if workload == "student":
        return {
            "input_audio_hours": None,
            "epochs": int(round(units)),
            "samples": None,
        }

    raise ValueError(workload)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--workload", choices=["teacher", "student"], required=True)
    p.add_argument("--units", type=float, required=True)
    p.add_argument("--job-spec", required=True)
    p.add_argument("--bucket", default=os.environ.get("HF_BUCKET"))
    p.add_argument(
        "--mode",
        choices=["advisory", "shadow", "active"],
        default="shadow",
    )
    args = p.parse_args()

    if not args.bucket:
        raise RuntimeError("HF_BUCKET or --bucket is required")

    if args.units <= 0:
        raise RuntimeError("--units must be > 0")

    with open(args.job_spec, "r", encoding="utf-8") as f:
        spec = json.load(f)

    context = spec.get("context") or {}
    accounting = spec.get("accounting") or infer_accounting(
        args.workload,
        args.units,
    )

    historical = call_historical(args.workload, args.units)
    model = ContextualModel.load_latest(args.bucket)

    feature_rows = []

    for candidate in historical["candidates"]:
        feature_rows.append(
            candidate_feature_row(
                workload=args.workload,
                provider=candidate["provider"],
                gpu_id=str(candidate.get("gpu_id", "unknown")),
                price_usd_per_hour=float(candidate["price_usd_per_hour"]),
                accounting=accounting,
                context=context,
            )
        )

    predictions = model.predict(feature_rows)

    enriched = []

    for candidate, pred in zip(historical["candidates"], predictions):
        runtime_hours = pred["predicted_runtime_seconds"] / 3600.0
        current_price = float(candidate["price_usd_per_hour"])

        # Two total-cost estimates:
        # 1) CatBoost direct cost model.
        # 2) Runtime-model * current price.
        dynamic_cost = runtime_hours * current_price
        direct_cost = pred["predicted_total_cost_usd"]

        # Blend them equally at first. This can later be calibrated.
        blended = 0.5 * direct_cost + 0.5 * dynamic_cost

        enriched.append(
            {
                **candidate,
                **pred,
                "runtime_times_current_price_usd": dynamic_cost,
                "contextual_blended_total_cost_usd": blended,
            }
        )

    enriched.sort(key=lambda x: x["contextual_blended_total_cost_usd"])
    contextual = enriched[0]

    if args.mode == "active":
        selected = contextual
        reason = "active_contextual_min_blended_cost"
    else:
        selected = historical["selected"]
        reason = f"{args.mode}_historical_paid_route"

    result = {
        "schema_version": "1.0",
        "job_id": spec.get("job_id"),
        "workload": args.workload,
        "units": args.units,
        "mode": args.mode,
        "model_version": model.metadata["model_version"],
        "historical_greedy": historical["selected"],
        "contextual_recommendation": contextual,
        "selected": selected,
        "selection_reason": reason,
        "candidates": enriched,
        "model_metrics": {
            "runtime": model.metadata["runtime_metrics"],
            "cost": model.metadata["cost_metrics"],
        },
    }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
