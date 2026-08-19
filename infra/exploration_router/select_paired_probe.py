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


def u01(job_id: str) -> float:
    h = hashlib.sha256(f"paired-probe:{job_id}".encode()).digest()
    return int.from_bytes(h[:8], "big") / float(2**64 - 1)


def ident(c: dict[str, Any]) -> str:
    return f"{c.get('provider')}::{c.get('gpu_id') or c.get('flavor')}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--workload", choices=["teacher", "student"], required=True)
    p.add_argument("--units", type=float, required=True)
    p.add_argument("--job-id", required=True)
    p.add_argument("--config", default="configs/exploration-router.yaml")
    args = p.parse_args()

    cfg = load_yaml(args.config)["paired_probe"]

    historical = call_historical(args.workload, args.units)
    candidates = list(historical["candidates"])
    primary = historical["selected"]

    out = {
        "schema_version": "1.0",
        "job_id": args.job_id,
        "workload": args.workload,
        "units": args.units,
        "run_probe": False,
        "primary": primary,
        "secondary": None,
        "reason": "disabled_or_not_safe",
        "assignment_value": None,
        "probability": float(cfg["probability"][args.workload]),
    }

    if not cfg.get("enabled", False):
        print(json.dumps(out, ensure_ascii=False))
        return

    if args.units > float(cfg["max_units"][args.workload]):
        out["reason"] = "job_too_large"
        print(json.dumps(out, ensure_ascii=False))
        return

    others = [c for c in candidates if ident(c) != ident(primary)]
    if not others:
        out["reason"] = "no_secondary_candidate"
        print(json.dumps(out, ensure_ascii=False))
        return

    others.sort(key=lambda c: float(c["risk_adjusted_total_cost_usd"]))
    secondary = others[0]

    extra = float(secondary["predicted_total_cost_usd"])
    if extra > float(cfg["max_extra_cost_usd"]):
        out["reason"] = "secondary_cost_guard"
        print(json.dumps(out, ensure_ascii=False))
        return

    u = u01(args.job_id)
    out["assignment_value"] = u
    out["secondary"] = secondary

    if u < out["probability"]:
        out["run_probe"] = True
        out["reason"] = "paired_probe_selected"
    else:
        out["reason"] = "paired_probe_not_selected"

    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
