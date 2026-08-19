#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
from statistics import mean, median

import yaml
from huggingface_hub import HfFileSystem


def percentile(values, p):
    if not values:
        return None
    xs = sorted(values)
    k = (len(xs) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return xs[int(k)]
    return xs[f] * (c - k) + xs[c] * (k - f)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", required=True)
    p.add_argument("--workload", choices=["teacher", "student"], required=True)
    p.add_argument("--config", default="configs/router-promotion.yaml")
    args = p.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))
    paths = fs.glob(f"hf://buckets/{args.bucket}/runs/*/routing-regret.json")

    rows = []
    for path in paths:
        try:
            with fs.open(path, "r") as f:
                row = json.load(f)
        except Exception:
            continue
        if row.get("workload") == args.workload and row.get("evaluable"):
            rows.append(row)

    min_runs = int(cfg["shadow"]["min_evaluable_runs"])
    coverage = (
        sum(1 for r in rows if r["shadow"].get("history_count", 0) > 0) / len(rows)
        if rows else 0.0
    )

    regrets = [float(r["predicted_regret_usd"]) for r in rows]
    rel = [
        float(r["relative_predicted_improvement"])
        for r in rows
        if r.get("relative_predicted_improvement") is not None
    ]
    same_route_errors = [
        float(r["same_route_prediction_error_ratio"])
        for r in rows
        if r.get("same_route_prediction_error_ratio") is not None
    ]

    mean_regret = mean(regrets) if regrets else None
    median_regret = median(regrets) if regrets else None
    mean_relative = mean(rel) if rel else None
    p95_error = percentile(same_route_errors, 0.95)

    reasons = []
    promote = True

    if len(rows) < min_runs:
        promote = False
        reasons.append(f"insufficient_runs:{len(rows)}<{min_runs}")

    if coverage < float(cfg["shadow"]["min_history_coverage"]):
        promote = False
        reasons.append("insufficient_history_coverage")

    if mean_regret is None or mean_regret < float(cfg["promotion"]["min_mean_regret_improvement_usd"]):
        promote = False
        reasons.append("mean_regret_improvement_below_threshold")

    if mean_relative is None or mean_relative < float(cfg["promotion"]["min_relative_cost_improvement"]):
        promote = False
        reasons.append("relative_cost_improvement_below_threshold")

    if cfg["promotion"].get("require_non_negative_median_improvement", True):
        if median_regret is None or median_regret < 0:
            promote = False
            reasons.append("median_improvement_negative")

    if p95_error is not None and p95_error > float(cfg["promotion"]["max_p95_absolute_prediction_error_ratio"]):
        promote = False
        reasons.append("prediction_error_too_high")

    report = {
        "schema_version": "1.0",
        "workload": args.workload,
        "evaluable_runs": len(rows),
        "history_coverage": coverage,
        "mean_predicted_regret_usd": mean_regret,
        "median_predicted_regret_usd": median_regret,
        "mean_relative_predicted_improvement": mean_relative,
        "p95_same_route_prediction_error_ratio": p95_error,
        "promote_historical_router": promote,
        "reasons": reasons,
        "thresholds": cfg
    }

    out_path = f"hf://buckets/{args.bucket}/router-evaluation/{args.workload}/promotion-report.json"
    fs.makedirs(out_path.rsplit("/", 1)[0], exist_ok=True)
    with fs.open(out_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
