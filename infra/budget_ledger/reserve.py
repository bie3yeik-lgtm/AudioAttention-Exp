#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from config import load_config, resolved_limits, resolved_pacing
from core import check_limits, pacing_checks, period_keys, reservation_state, scope_names
from storage import append_event, load_events


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", default=os.environ.get("HF_BUCKET"))
    p.add_argument("--job-id", required=True)
    p.add_argument("--workload", required=True)
    p.add_argument("--amount-usd", type=float, required=True)
    p.add_argument("--provider")
    p.add_argument("--gpu-id")
    p.add_argument("--config", default="configs/budget-ledger.yaml")
    args = p.parse_args()

    if not args.bucket:
        raise RuntimeError("HF_BUCKET or --bucket is required")
    if args.amount_usd < 0:
        raise RuntimeError("Reservation amount must be >= 0")

    cfg = load_config(args.config)
    storage_prefix = cfg["storage"]["prefix"]
    events = load_events(args.bucket, storage_prefix)
    state = reservation_state(events).get(args.job_id)

    if state and state.get("settlement"):
        raise RuntimeError(f"Job {args.job_id} is already settled")
    if state and state.get("reservation") and not state.get("release"):
        print(json.dumps({"status": "already_reserved", "reservation": state["reservation"]}, ensure_ascii=False))
        return
    if state and state.get("release"):
        raise RuntimeError(
            f"Job {args.job_id} was released; use a new job_id for a new reservation"
        )

    now = datetime.now(timezone.utc)
    periods = period_keys(now, cfg["timezone"])
    limits = resolved_limits(cfg)
    pacing = resolved_pacing(cfg)
    checks = check_limits(
        events,
        workload=args.workload,
        amount_usd=args.amount_usd,
        periods=periods,
        limits=limits,
    )
    pace_checks = pacing_checks(
        events,
        workload=args.workload,
        amount_usd=args.amount_usd,
        now=now,
        tz_name=cfg["timezone"],
        limits=limits,
        pacing=pacing,
    )
    denied = [x for x in checks if not x["allowed"]]
    pacing_denied = [x for x in pace_checks if not x["allowed"]]
    if denied or pacing_denied:
        print(
            json.dumps(
                {
                    "status": "denied",
                    "checks": checks,
                    "pacing": pacing,
                    "pacing_checks": pace_checks,
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(3)

    event = {
        "event_type": "reservation",
        "reservation_id": args.job_id,
        "job_id": args.job_id,
        "workload": args.workload,
        "reserved_cost_usd": args.amount_usd,
        "provider": args.provider,
        "gpu_id": args.gpu_id,
        "periods": periods,
        "scopes": scope_names(args.workload),
        "ttl_hours": int(cfg["reservation"]["ttl_hours"]),
    }
    path = append_event(args.bucket, storage_prefix, event)
    print(json.dumps({"status": "reserved", "path": path, "event": event, "checks": checks, "pacing": pacing, "pacing_checks": pace_checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
