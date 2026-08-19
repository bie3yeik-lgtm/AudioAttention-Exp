#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from statistics import mean

import yaml
from huggingface_hub import HfFileSystem

from model import ConformalCalibration


def load_json(fs, path):
    try:
        with fs.open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", required=True)
    p.add_argument("--workload", choices=["teacher", "student"], required=True)
    p.add_argument("--config", default="configs/conformal-router.yaml")
    args = p.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    cal = ConformalCalibration.load_latest(
        args.bucket,
        config_path=args.config,
    )

    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))
    paths = fs.glob(
        f"hf://buckets/{args.bucket}/runs/*/contextual-evaluation.json"
    )

    rows = []

    for path in paths:
        ev = load_json(fs, path)
        if not ev or ev.get("workload") != args.workload:
            continue

        contextual = ev.get("contextual") or {}
        actual = ev.get("actual") or {}

        if not contextual.get("same_route"):
            continue

        pred_cost = float(contextual["predicted_cost_usd"])
        pred_runtime = float(contextual["predicted_runtime_seconds"])

        bounds = cal.bounds(
            workload=args.workload,
            provider=actual["provider"],
            gpu_id=str(actual["gpu_id"]),
            predicted_cost_usd=pred_cost,
            predicted_runtime_seconds=pred_runtime,
        )

        actual_cost = float(actual["cost_usd"])
        actual_runtime = float(actual["runtime_seconds"])

        cost_hit = (
            bounds["cost_lower_usd"]
            <= actual_cost
            <= bounds["cost_upper_usd"]
        )
        runtime_hit = (
            bounds["runtime_lower_seconds"]
            <= actual_runtime
            <= bounds["runtime_upper_seconds"]
        )

        rel_width = (
            (bounds["cost_upper_usd"] - bounds["cost_lower_usd"])
            / pred_cost
            if pred_cost > 0 else None
        )

        rows.append(
            {
                "cost_hit": cost_hit,
                "runtime_hit": runtime_hit,
                "relative_width": rel_width,
            }
        )

    if not rows:
        raise RuntimeError("No evaluable coverage rows")

    cost_coverage = mean(1.0 if r["cost_hit"] else 0.0 for r in rows)
    runtime_coverage = mean(
        1.0 if r["runtime_hit"] else 0.0 for r in rows
    )
    widths = [
        r["relative_width"]
        for r in rows
        if r["relative_width"] is not None
    ]

    mean_width = mean(widths) if widths else None

    pcfg = cfg["promotion"]
    promote = True
    reasons = []

    if len(rows) < int(pcfg["min_evaluation_records"]):
        promote = False
        reasons.append("insufficient_evaluation_records")

    if not (
        float(pcfg["min_empirical_coverage"])
        <= cost_coverage
        <= float(pcfg["max_empirical_coverage"])
    ):
        promote = False
        reasons.append("cost_coverage_outside_target_band")

    if (
        mean_width is None
        or mean_width
        > float(pcfg["max_mean_relative_interval_width"])
    ):
        promote = False
        reasons.append("intervals_too_wide")

    report = {
        "schema_version": "1.0",
        "workload": args.workload,
        "records": len(rows),
        "nominal_coverage": cal.payload["coverage"],
        "empirical_cost_coverage": cost_coverage,
        "empirical_runtime_coverage": runtime_coverage,
        "mean_relative_cost_interval_width": mean_width,
        "promote_conformal_router": promote,
        "reasons": reasons,
        "thresholds": pcfg,
    }

    out_path = (
        f"hf://buckets/{args.bucket}/router-evaluation/"
        f"{args.workload}/conformal-promotion-report.json"
    )
    fs.makedirs(out_path.rsplit("/", 1)[0], exist_ok=True)
    with fs.open(out_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
