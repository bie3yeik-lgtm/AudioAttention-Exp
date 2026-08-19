#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict

from huggingface_hub import HfFileSystem


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", required=True)
    p.add_argument("--workload", choices=["teacher", "student"], required=True)
    args = p.parse_args()

    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))
    paths = fs.glob(
        f"hf://buckets/{args.bucket}/runs/*/bandit-decision.json"
    )

    rows = []
    for path in paths:
        try:
            with fs.open(path, "r") as f:
                row = json.load(f)
        except Exception:
            continue

        if row.get("workload") == args.workload:
            rows.append(row)

    changed = 0
    active = 0
    gate_downgrades = 0

    by_gpu = defaultdict(
        lambda: {
            "recommended": 0,
            "selected": 0,
        }
    )

    for row in rows:
        h = row["historical_greedy"]
        b = row["bandit_recommendation"]
        s = row["selected"]

        hid = f"{h['provider']}::{h.get('gpu_id')}"
        bid = f"{b['provider']}::{b.get('gpu_id')}"
        sid = f"{s['provider']}::{s.get('gpu_id')}"

        by_gpu[bid]["recommended"] += 1
        by_gpu[sid]["selected"] += 1

        if hid != bid:
            changed += 1

        if row.get("effective_mode") == "active":
            active += 1

        if (
            row.get("requested_mode") == "active"
            and row.get("effective_mode") != "active"
        ):
            gate_downgrades += 1

    out = {
        "workload": args.workload,
        "decisions": len(rows),
        "bandit_differs_from_historical": changed,
        "bandit_difference_rate": changed / len(rows) if rows else 0.0,
        "active_decisions": active,
        "active_gate_downgrades": gate_downgrades,
        "candidate_usage": dict(by_gpu),
    }

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
