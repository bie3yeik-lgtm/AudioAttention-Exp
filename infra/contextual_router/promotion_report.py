#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
from statistics import mean, median
from typing import Any

import yaml
from huggingface_hub import HfFileSystem


def safe_mean(values):
    xs = [float(x) for x in values if x is not None]
    return mean(xs) if xs else None


def safe_median(values):
    xs = [float(x) for x in values if x is not None]
    return median(xs) if xs else None


def load_json(fs, path):
    try:
        with fs.open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def ident(obj: dict[str, Any]) -> str:
    return f"{obj.get('provider')}::{obj.get('gpu_id') or 'unknown'}"


def paired_accuracy(
    fs: HfFileSystem,
    bucket: str,
    workload: str,
    decision_rows: list[dict[str, Any]],
) -> tuple[float | None, int]:
    """
    Evaluate Contextual winner predictions against measured paired probes.

    Matching is by provider/GPU pair and workload. Because paired probes are
    intentionally small benchmark jobs, this is a coarse route-ranking check,
    not exact per-job calibration.
    """
    paths = fs.glob(
        f"hf://buckets/{bucket}/router-evaluation/"
        f"{workload}/paired/*.json"
    )

    if not paths or not decision_rows:
        return None, 0

    # Latest contextual preference by route pair.
    preferences = {}
    for row in decision_rows:
        decision_path = (
            f"hf://buckets/{bucket}/runs/"
            f"{row['job_id']}/contextual-decision.json"
        )
        d = load_json(fs, decision_path)
        if not d:
            continue

        h = d.get("historical_greedy") or {}
        c = d.get("contextual_recommendation") or {}

        if not h or not c:
            continue

        pair = frozenset([ident(h), ident(c)])
        if len(pair) == 2:
            preferences[pair] = ident(c)

    correct = 0
    total = 0

    for path in paths:
        probe = load_json(fs, path)
        if not probe or not probe.get("measured_counterfactual"):
            continue

        p = probe["primary"]
        s = probe["secondary"]

        pair = frozenset([ident(p), ident(s)])
        predicted = preferences.get(pair)
        if not predicted:
            continue

        winner_obj = p if probe["winner"] == "primary" else s
        actual_winner = ident(winner_obj)

        total += 1
        if predicted == actual_winner:
            correct += 1

    return (correct / total if total else None), total


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", required=True)
    p.add_argument("--workload", choices=["teacher", "student"], required=True)
    p.add_argument(
        "--config",
        default="configs/contextual-promotion.yaml",
    )
    args = p.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))

    all_cost_paths = fs.glob(
        f"hf://buckets/{args.bucket}/runs/*/cost.json"
    )
    eval_paths = fs.glob(
        f"hf://buckets/{args.bucket}/runs/*/contextual-evaluation.json"
    )

    rows = []
    for path in eval_paths:
        row = load_json(fs, path)
        if row and row.get("workload") == args.workload and row.get("evaluable"):
            rows.append(row)

    workload_cost_count = 0
    for path in all_cost_paths:
        cost = load_json(fs, path)
        if cost and cost.get("workload") == args.workload:
            workload_cost_count += 1

    coverage = (
        len(rows) / workload_cost_count
        if workload_cost_count > 0 else 0.0
    )

    contextual_cost_apes = [
        r["contextual"]["cost_ape"]
        for r in rows
        if r["contextual"].get("cost_ape") is not None
    ]
    contextual_runtime_apes = [
        r["contextual"]["runtime_ape"]
        for r in rows
        if r["contextual"].get("runtime_ape") is not None
    ]

    both_same = [r for r in rows if r.get("both_same_route")]
    error_deltas = [
        r["contextual_minus_historical_abs_cost_error_usd"]
        for r in both_same
        if r.get("contextual_minus_historical_abs_cost_error_usd") is not None
    ]

    historical_errors = [
        r["historical"]["cost_absolute_error_usd"]
        for r in both_same
        if r["historical"].get("cost_absolute_error_usd") is not None
    ]
    contextual_errors = [
        r["contextual"]["cost_absolute_error_usd"]
        for r in both_same
        if r["contextual"].get("cost_absolute_error_usd") is not None
    ]

    historical_mae = safe_mean(historical_errors)
    contextual_mae = safe_mean(contextual_errors)

    mae_improvement_ratio = None
    if historical_mae is not None and historical_mae > 0 and contextual_mae is not None:
        mae_improvement_ratio = (
            historical_mae - contextual_mae
        ) / historical_mae

    paired_acc, paired_count = paired_accuracy(
        fs,
        args.bucket,
        args.workload,
        rows,
    )

    ecfg = cfg["evaluation"]
    pcfg = cfg["promotion"]

    reasons = []
    promote = True

    if len(rows) < int(ecfg["min_evaluable_runs"]):
        promote = False
        reasons.append(
            f"insufficient_evaluable_runs:{len(rows)}"
            f"<{int(ecfg['min_evaluable_runs'])}"
        )

    if len(both_same) < int(ecfg["min_same_route_runs"]):
        promote = False
        reasons.append(
            f"insufficient_same_route_runs:{len(both_same)}"
            f"<{int(ecfg['min_same_route_runs'])}"
        )

    if paired_count < int(ecfg["min_paired_probes"]):
        promote = False
        reasons.append(
            f"insufficient_paired_probes:{paired_count}"
            f"<{int(ecfg['min_paired_probes'])}"
        )

    if coverage < float(pcfg["min_evaluation_coverage"]):
        promote = False
        reasons.append("evaluation_coverage_below_threshold")

    contextual_cost_mape = safe_mean(contextual_cost_apes)
    contextual_runtime_mape = safe_mean(contextual_runtime_apes)

    if (
        contextual_cost_mape is None
        or contextual_cost_mape > float(pcfg["max_contextual_cost_mape"])
    ):
        promote = False
        reasons.append("contextual_cost_mape_too_high")

    if (
        contextual_runtime_mape is None
        or contextual_runtime_mape > float(pcfg["max_contextual_runtime_mape"])
    ):
        promote = False
        reasons.append("contextual_runtime_mape_too_high")

    if (
        mae_improvement_ratio is None
        or mae_improvement_ratio
        < float(pcfg["min_mean_absolute_error_improvement_ratio"])
    ):
        promote = False
        reasons.append("mae_improvement_below_threshold")

    median_delta = safe_median(error_deltas)
    if pcfg.get("require_non_negative_median_error_improvement", True):
        # delta < 0 means contextual absolute error is lower.
        if median_delta is None or median_delta > 0:
            promote = False
            reasons.append("median_error_improvement_negative")

    if (
        paired_acc is None
        or paired_acc < float(pcfg["min_paired_winner_accuracy"])
    ):
        promote = False
        reasons.append("paired_winner_accuracy_below_threshold")

    report = {
        "schema_version": "1.0",
        "workload": args.workload,
        "evaluable_runs": len(rows),
        "same_route_runs": len(both_same),
        "evaluation_coverage": coverage,

        "contextual_cost_mape": contextual_cost_mape,
        "contextual_runtime_mape": contextual_runtime_mape,

        "historical_same_route_cost_mae_usd": historical_mae,
        "contextual_same_route_cost_mae_usd": contextual_mae,
        "mean_absolute_error_improvement_ratio": mae_improvement_ratio,
        "median_contextual_minus_historical_abs_error_usd": median_delta,

        "paired_winner_accuracy": paired_acc,
        "paired_winner_evaluations": paired_count,

        "promote_contextual_router": promote,
        "reasons": reasons,
        "thresholds": cfg,
    }

    out_path = (
        f"hf://buckets/{args.bucket}/router-evaluation/"
        f"{args.workload}/contextual-promotion-report.json"
    )
    fs.makedirs(out_path.rsplit("/", 1)[0], exist_ok=True)

    with fs.open(out_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
