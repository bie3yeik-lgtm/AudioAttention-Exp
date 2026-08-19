#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from config import load_config, resolved_forecast, resolved_limits, resolved_pacing
from core import forecast_aware_pacing_checks, period_keys, scope_names, usage_for_period
from storage import load_events
from forecast import load_schedule


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
    pacing = resolved_pacing(cfg)
    forecast_cfg = resolved_forecast(cfg)
    schedule = load_schedule(forecast_cfg["schedule_file"])
    events = load_events(args.bucket, cfg["storage"]["prefix"])
    periods = period_keys(datetime.now(timezone.utc), cfg["timezone"])
    scopes = ["global"] + ([f"workload:{args.workload}"] if args.workload else ["workload:teacher", "workload:student"])
    report = {"periods": periods, "pacing": pacing, "forecast": forecast_cfg, "scopes": {}}
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
        workload_for_scope = args.workload if args.workload else (scope.split(":", 1)[1] if scope.startswith("workload:") else "teacher")
        pace = forecast_aware_pacing_checks(
            events,
            workload=workload_for_scope,
            amount_usd=0.0,
            now=datetime.now(timezone.utc),
            tz_name=cfg["timezone"],
            limits=limits,
            pacing=pacing,
            forecast_cfg=forecast_cfg,
            schedule=schedule,
        )
        matching = [x for x in pace if x["scope"] == scope]
        if matching:
            s["pacing"] = matching[0]
        report["scopes"][scope] = s
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
