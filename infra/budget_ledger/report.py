#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from config import load_config, resolved_limits
from core import period_keys, scope_names, usage_for_period
from storage import load_events


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", default=os.environ.get("HF_BUCKET"))
    p.add_argument("--workload", choices=["teacher", "student"])
    p.add_argument("--config", default="configs/budget-ledger.yaml")
    args = p.parse_args()
    if not args.bucket:
        raise RuntimeError("HF_BUCKET or --bucket is required")

    cfg = load_config(args.config)
    limits = resolved_limits(cfg)
    events = load_events(args.bucket, cfg["storage"]["prefix"])
    periods = period_keys(datetime.now(timezone.utc), cfg["timezone"])
    scopes = ["global"] + ([f"workload:{args.workload}"] if args.workload else ["workload:teacher", "workload:student"])
    report = {"periods": periods, "scopes": {}}
    for scope in scopes:
        s = {}
        for ptype, pkey in periods.items():
            usage = usage_for_period(events, period_type=ptype, period_key=pkey, scope=scope)
            cap = limits.get(scope, {}).get(ptype)
            s[ptype] = {
                "period_key": pkey,
                **usage,
                "limit_usd": cap,
                "remaining_usd": None if cap is None else float(cap) - usage["committed_usd"],
            }
        report["scopes"][scope] = s
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
