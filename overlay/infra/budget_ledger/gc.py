#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone, timedelta

from config import load_config
from core import open_reservations, parse_iso
from storage import append_event, load_events


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", default=os.environ.get("HF_BUCKET"))
    p.add_argument("--config", default="configs/budget-ledger.yaml")
    args = p.parse_args()
    if not args.bucket:
        raise RuntimeError("HF_BUCKET or --bucket is required")

    cfg = load_config(args.config)
    storage_prefix = cfg["storage"]["prefix"]
    events = load_events(args.bucket, storage_prefix)
    now = datetime.now(timezone.utc)
    released = []

    for reservation in open_reservations(events):
        ttl = int(reservation.get("ttl_hours", cfg["reservation"]["ttl_hours"]))
        created = parse_iso(reservation["created_at"])
        if now < created + timedelta(hours=ttl):
            continue
        event = {
            "event_type": "release",
            "reservation_id": reservation["reservation_id"],
            "job_id": reservation["job_id"],
            "workload": reservation["workload"],
            "released_cost_usd": float(reservation["reserved_cost_usd"]),
            "reason": "reservation_ttl_expired",
            "periods": reservation["periods"],
            "scopes": reservation["scopes"],
        }
        path = append_event(args.bucket, storage_prefix, event)
        released.append({"job_id": reservation["job_id"], "path": path})

    print(json.dumps({"released": released, "count": len(released)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
