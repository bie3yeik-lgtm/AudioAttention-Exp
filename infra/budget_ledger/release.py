#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os

from config import load_config
from core import reservation_state
from storage import append_event, load_events


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", default=os.environ.get("HF_BUCKET"))
    p.add_argument("--job-id", required=True)
    p.add_argument("--reason", default="manual_release")
    p.add_argument("--config", default="configs/budget-ledger.yaml")
    args = p.parse_args()

    if not args.bucket:
        raise RuntimeError("HF_BUCKET or --bucket is required")
    cfg = load_config(args.config)
    storage_prefix = cfg["storage"]["prefix"]
    events = load_events(args.bucket, storage_prefix)
    state = reservation_state(events).get(args.job_id)
    if not state or not state.get("reservation"):
        print(json.dumps({"status": "not_reserved"}))
        return
    if state.get("settlement"):
        print(json.dumps({"status": "already_settled"}))
        return
    if state.get("release"):
        print(json.dumps({"status": "already_released"}))
        return

    reservation = state["reservation"]
    event = {
        "event_type": "release",
        "reservation_id": args.job_id,
        "job_id": args.job_id,
        "workload": reservation["workload"],
        "released_cost_usd": float(reservation["reserved_cost_usd"]),
        "reason": args.reason,
        "periods": reservation["periods"],
        "scopes": reservation["scopes"],
    }
    path = append_event(args.bucket, storage_prefix, event)
    print(json.dumps({"status": "released", "path": path, "event": event}, ensure_ascii=False))


if __name__ == "__main__":
    main()
