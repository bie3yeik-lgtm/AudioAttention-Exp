#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any

import yaml

from conformal_gate import conformal_is_promoted
from policy import BudgetError, apply_budget_policy, parse_budget


def load_yaml(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def call_bandit(
    *,
    workload: str,
    units: float,
    job_id: str,
    job_spec: str,
    bucket: str,
    prediction_source: str,
    mode: str,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        "infra/budget_router:"
        "infra/bandit_router:"
        "infra/historical_router:"
        "infra/contextual_router:"
        "infra/residual_calibration:"
        "infra/conformal_router:"
        + env.get("PYTHONPATH", "")
    )

    p = subprocess.run(
        [
            sys.executable,
            "infra/bandit_router/select_bandit.py",
            "--workload",
            workload,
            "--units",
            str(units),
            "--job-id",
            job_id,
            "--job-spec",
            job_spec,
            "--prediction-source",
            prediction_source,
            "--mode",
            mode,
            "--bucket",
            bucket,
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip())

    return json.loads(p.stdout)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--workload", choices=["teacher", "student"], required=True)
    p.add_argument("--units", type=float, required=True)
    p.add_argument("--job-id", required=True)
    p.add_argument("--job-spec", required=True)
    p.add_argument("--bucket", default=os.environ.get("HF_BUCKET"))
    p.add_argument(
        "--prediction-source",
        choices=["auto", "historical", "contextual"],
        default="auto",
    )
    p.add_argument(
        "--bandit-mode",
        choices=["advisory", "shadow", "active"],
        default="shadow",
    )
    p.add_argument(
        "--config",
        default="configs/budget-router.yaml",
    )
    args = p.parse_args()

    if not args.bucket:
        raise RuntimeError("HF_BUCKET or --bucket is required")

    cfg = load_yaml(args.config)

    with open(args.job_spec, "r", encoding="utf-8") as f:
        job_spec = json.load(f)

    budget = parse_budget(job_spec, cfg["defaults"])

    bandit = call_bandit(
        workload=args.workload,
        units=args.units,
        job_id=args.job_id,
        job_spec=args.job_spec,
        bucket=args.bucket,
        prediction_source=args.prediction_source,
        mode=args.bandit_mode,
    )

    promoted, conformal_report = conformal_is_promoted(
        args.bucket,
        args.workload,
    )

    if (
        budget["mode"] == "hard_budget"
        and cfg["policy"].get(
            "require_promoted_conformal_for_hard_budget",
            True,
        )
        and not promoted
    ):
        raise BudgetError(
            "Hard budget requires promoted conformal calibration"
        )

    candidates = bandit["candidates"]

    evaluated = apply_budget_policy(
        candidates,
        budget=budget,
        tolerance_usd=float(
            cfg["policy"]["budget_tolerance_usd"]
        ),
        require_conformal_for_hard=bool(
            cfg["policy"]["require_conformal_for_hard_budget"]
        ),
        soft_use_upper_excess=bool(
            cfg["policy"]["soft_budget_use_upper_bound_excess"]
        ),
    )

    feasible = [c for c in evaluated if c["budget_feasible"]]

    if budget["mode"] == "hard_budget":
        feasible.sort(
            key=lambda c: (
                float(c["budget_score_usd"]),
                float(c.get("bandit_lcb_score_usd", float("inf"))),
            )
        )
    else:
        feasible.sort(
            key=lambda c: (
                float(c["budget_score_usd"]),
                float(c.get("bandit_lcb_score_usd", float("inf"))),
            )
        )

    if not feasible:
        if cfg["policy"].get("fail_closed_if_no_candidate", True):
            raise BudgetError(
                "No candidate satisfies the configured budget policy"
            )

        selected = bandit["selected"]
        reason = "budget_no_candidate_fallback_bandit"
    else:
        selected = feasible[0]
        reason = f"budget_{budget['mode']}_selection"

    result = {
        "schema_version": "1.0",
        "job_id": args.job_id,
        "workload": args.workload,
        "units": args.units,

        "budget": budget,
        "conformal_promoted": promoted,
        "conformal_promotion_report": conformal_report,

        "bandit_effective_mode": bandit["effective_mode"],
        "prediction_source": bandit.get("prediction_source"),

        "selected": selected,
        "selection_reason": reason,
        "candidates": evaluated,
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
