#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from typing import Any

import yaml


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


def deterministic_uniform(job_id: str, salt: str) -> float:
    digest = hashlib.sha256(f"{salt}:{job_id}".encode()).digest()
    n = int.from_bytes(digest[:8], "big")
    return n / float(2**64 - 1)


def candidate_identity(candidate: dict[str, Any]) -> str:
    return f"{candidate.get('provider')}::{candidate.get('gpu_id') or candidate.get('flavor')}"


def choose_exploration_candidate(
    candidates: list[dict[str, Any]],
    greedy: dict[str, Any],
    target_history: int,
) -> dict[str, Any] | None:
    alternatives = [
        c for c in candidates
        if candidate_identity(c) != candidate_identity(greedy)
    ]
    if not alternatives:
        return None

    # Explore under-observed candidates first. Break ties by predicted risk-adjusted cost.
    alternatives.sort(
        key=lambda c: (
            int(c.get("history_count", 0)),
            float(c.get("risk_adjusted_total_cost_usd", float("inf"))),
        )
    )
    return alternatives[0]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--workload", choices=["teacher", "student"], required=True)
    p.add_argument("--units", type=float, required=True)
    p.add_argument("--job-id", required=True)
    p.add_argument("--config", default="configs/exploration-router.yaml")
    args = p.parse_args()

    if args.units <= 0:
        raise RuntimeError("--units must be > 0")

    cfg = load_yaml(args.config)
    policy = cfg["policy"]

    historical = call_historical(args.workload, args.units)
    candidates = historical["candidates"]
    greedy = historical["selected"]

    result: dict[str, Any] = {
        "schema_version": "1.0",
        "job_id": args.job_id,
        "workload": args.workload,
        "units": args.units,
        "mode": "exploit",
        "greedy": greedy,
        "selected": greedy,
        "exploration_probability": 0.0,
        "assignment_value": None,
        "reason": "exploration_disabled_or_not_safe",
        "historical": historical,
    }

    if not policy.get("enabled", False):
        print(json.dumps(result, ensure_ascii=False))
        return

    epsilon = float(policy["epsilon"][args.workload])
    max_units = float(policy["max_units"][args.workload])

    if args.units > max_units:
        result["reason"] = "job_too_large_for_exploration"
        print(json.dumps(result, ensure_ascii=False))
        return

    alt = choose_exploration_candidate(
        candidates,
        greedy,
        int(policy["underexplored_history_target"]),
    )

    if alt is None:
        result["reason"] = "no_alternative_candidate"
        print(json.dumps(result, ensure_ascii=False))
        return

    greedy_cost = float(greedy["predicted_total_cost_usd"])
    alt_cost = float(alt["predicted_total_cost_usd"])
    extra = max(0.0, alt_cost - greedy_cost)
    relative = extra / greedy_cost if greedy_cost > 0 else float("inf")

    if extra > float(policy["max_predicted_extra_cost_usd"]):
        result["reason"] = "alternative_exceeds_absolute_cost_guard"
        print(json.dumps(result, ensure_ascii=False))
        return

    if relative > float(policy["max_predicted_relative_premium"]):
        result["reason"] = "alternative_exceeds_relative_cost_guard"
        print(json.dumps(result, ensure_ascii=False))
        return

    u = deterministic_uniform(args.job_id, "exploration")
    result["assignment_value"] = u
    result["exploration_probability"] = epsilon

    if u < epsilon:
        result["mode"] = "explore"
        result["selected"] = alt
        result["reason"] = "epsilon_exploration"
    else:
        result["reason"] = "epsilon_exploitation"

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
