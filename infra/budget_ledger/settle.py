#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os

from config import load_config
from core import reservation_state
from storage import append_event, fs, load_events


def read_cost(bucket: str, job_id: str) -> dict:
    path = f"hf://buckets/{bucket}/runs/{job_id}/cost.json"
    with fs().open(path, "r") as f:
        return json.load(f)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", default=os.environ.get("HF_BUCKET"))
    p.add_argument("--job-id", required=True)
    p.add_argument("--actual-cost-usd", type=float)
    p.add_argument("--config", default="configs/budget-ledger.yaml")
    args = p.parse_args()

    if not args.bucket:
        raise RuntimeError("HF_BUCKET or --bucket is required")

    cfg = load_config(args.config)
    storage_prefix = cfg["storage"]["prefix"]
    events = load_events(args.bucket, storage_prefix)
    state = reservation_state(events).get(args.job_id)
    if not state or not state.get("reservation"):
        raise RuntimeError(f"No reservation for {args.job_id}")
    if state.get("settlement"):
        print(json.dumps({"status": "already_settled", "settlement": state["settlement"]}, ensure_ascii=False))
        return

    cost = read_cost(args.bucket, args.job_id) if args.actual_cost_usd is None else None
    actual = float(args.actual_cost_usd if args.actual_cost_usd is not None else cost["estimated_cost_usd"])
    reservation = state["reservation"]
    event = {
        "event_type": "settlement",
        "reservation_id": args.job_id,
        "job_id": args.job_id,
        "workload": reservation["workload"],
        "actual_cost_usd": actual,
        "reserved_cost_usd": float(reservation["reserved_cost_usd"]),
        "variance_usd": actual - float(reservation["reserved_cost_usd"]),
        "periods": reservation["periods"],
        "scopes": reservation["scopes"],
    }
    path = append_event(args.bucket, storage_prefix, event)
    print(json.dumps({"status": "settled", "path": path, "event": event}, ensure_ascii=False))


if __name__ == "__main__":
    main()
