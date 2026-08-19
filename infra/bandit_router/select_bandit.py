#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any

import yaml

from evidence import (
    count_paired_probes,
    load_paired_evidence,
    read_promotion_report,
)
from prediction_source import choose_prediction_candidates
from score import (
    bandit_score,
    candidate_key,
    is_safe_alternative,
    uncertainty_fraction,
)


def load_yaml(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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


def resolve_mode(
    requested: str,
    *,
    bucket: str,
    workload: str,
    cfg: dict[str, Any],
) -> tuple[str, list[str], dict[str, Any] | None, int]:
    reasons: list[str] = []
    gate = cfg["promotion_gate"]

    promotion = read_promotion_report(bucket, workload)
    paired_count = count_paired_probes(bucket, workload)

    if requested != "active":
        return requested, reasons, promotion, paired_count

    if gate.get("require_historical_promotion_for_active", True):
        if not promotion or not promotion.get("promote_historical_router", False):
            reasons.append("historical_router_not_promoted")

    required_pairs = int(gate["min_paired_probes_for_active"][workload])
    if paired_count < required_pairs:
        reasons.append(
            f"insufficient_paired_probes:{paired_count}<{required_pairs}"
        )

    if reasons and gate.get("fail_closed_to_shadow", True):
        return "shadow", reasons, promotion, paired_count

    return requested, reasons, promotion, paired_count


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--workload", choices=["teacher", "student"], required=True)
    p.add_argument("--units", type=float, required=True)
    p.add_argument("--job-id", required=True)
    p.add_argument("--job-spec")
    p.add_argument(
        "--prediction-source",
        choices=["auto", "historical", "contextual"],
        default="auto",
    )
    p.add_argument("--bucket", default=os.environ.get("HF_BUCKET"))
    p.add_argument(
        "--mode",
        choices=["advisory", "shadow", "active"],
        default=None,
    )
    p.add_argument("--config", default="configs/bandit-router.yaml")
    args = p.parse_args()

    if not args.bucket:
        raise RuntimeError("HF_BUCKET or --bucket is required")

    if args.units <= 0:
        raise RuntimeError("--units must be > 0")

    cfg = load_yaml(args.config)
    policy = cfg["policy"][args.workload]
    evidence_cfg = cfg["evidence"]

    requested_mode = args.mode or os.environ.get(
        "BANDIT_ROUTER_MODE",
        cfg["mode"]["default"],
    )

    effective_mode, gate_reasons, promotion, paired_count = resolve_mode(
        requested_mode,
        bucket=args.bucket,
        workload=args.workload,
        cfg=cfg,
    )

    historical = call_historical(args.workload, args.units)

    routed_candidates, prediction_source_name, contextual_report = (
        choose_prediction_candidates(
            workload=args.workload,
            bucket=args.bucket,
            historical_result=historical,
            units=args.units,
            job_spec=args.job_spec,
            requested_source=args.prediction_source,
        )
    )

    # Historical greedy remains the safe baseline even when Contextual
    # predictions are promoted and used for Bandit ranking.
    greedy = historical["selected"]

    paired = load_paired_evidence(args.bucket, workload=args.workload)

    scored: list[dict[str, Any]] = []

    for raw in routed_candidates:
        key = candidate_key(raw)

        frac, saturation = uncertainty_fraction(
            raw,
            paired.get(key),
            paired_weight=float(evidence_cfg["paired_observation_weight"]),
            saturation_observations=float(
                evidence_cfg["saturation_observations"]
            ),
            minimum_fraction=float(
                evidence_cfg["minimum_uncertainty_fraction"]
            ),
            cold_start_fraction=float(
                evidence_cfg["cold_start_uncertainty_fraction"]
            ),
        )

        candidate = bandit_score(
            raw,
            uncertainty_fraction_value=frac,
            beta=float(policy["exploration_strength_beta"]),
        )

        candidate["evidence_saturation"] = saturation
        candidate["paired_evidence"] = paired.get(
            key,
            {
                "paired_observations": 0,
                "paired_wins": 0,
                "paired_losses": 0,
            },
        )

        safe, guard_reason = is_safe_alternative(
            candidate,
            greedy,
            max_extra_cost_usd=float(
                policy["max_predicted_extra_cost_usd"]
            ),
            max_relative_premium=float(
                policy["max_predicted_relative_premium"]
            ),
        )

        # Greedy is always safe because it is the historical baseline.
        if candidate_key(candidate) == candidate_key(greedy):
            safe = True
            guard_reason = "historical_greedy"

        if args.units > float(policy["max_units_for_exploration"]):
            if candidate_key(candidate) != candidate_key(greedy):
                safe = False
                guard_reason = "job_too_large_for_bandit_exploration"

        candidate["bandit_safe"] = safe
        candidate["bandit_guard_reason"] = guard_reason

        scored.append(candidate)

    safe_candidates = [x for x in scored if x["bandit_safe"]]
    safe_candidates.sort(key=lambda x: x["bandit_lcb_score_usd"])

    recommendation = safe_candidates[0] if safe_candidates else greedy

    if effective_mode == "active":
        selected = recommendation
        selection_reason = "active_bandit_lcb"
    else:
        # Advisory/shadow never changes paid execution.
        selected = greedy
        selection_reason = f"{effective_mode}_historical_greedy"

    result = {
        "schema_version": "1.0",
        "job_id": args.job_id,
        "workload": args.workload,
        "units": args.units,

        "requested_mode": requested_mode,
        "effective_mode": effective_mode,
        "promotion_gate_reasons": gate_reasons,

        "historical_greedy": greedy,
        "bandit_recommendation": recommendation,
        "selected": selected,

        "prediction_source": prediction_source_name,
        "contextual_promotion_report": contextual_report,

        "selection_reason": selection_reason,
        "paired_probe_count": paired_count,
        "historical_promotion_report": promotion,

        "candidates": scored,
    }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
