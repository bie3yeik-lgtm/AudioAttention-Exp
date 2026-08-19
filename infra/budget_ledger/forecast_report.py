#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from config import load_config, resolved_forecast, resolved_limits, resolved_pacing
from core import forecast_aware_pacing_checks
from forecast import load_schedule
from storage import load_events


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", default=os.environ.get("HF_BUCKET"))
    p.add_argument("--workload", choices=["teacher", "student"], required=True)
    p.add_argument("--config", default="configs/budget-ledger.yaml")
    args = p.parse_args()

    if not args.bucket:
        raise RuntimeError("HF_BUCKET or --bucket is required")

    cfg = load_config(args.config)
    forecast_cfg = resolved_forecast(cfg)
    schedule = load_schedule(forecast_cfg["schedule_file"])
    events = load_events(args.bucket, cfg["storage"]["prefix"])

    checks = forecast_aware_pacing_checks(
        events,
        workload=args.workload,
        amount_usd=0.0,
        now=datetime.now(timezone.utc),
        tz_name=cfg["timezone"],
        limits=resolved_limits(cfg),
        pacing=resolved_pacing(cfg),
        forecast_cfg=forecast_cfg,
        schedule=schedule,
    )

    print(
        json.dumps(
            {
                "workload": args.workload,
                "forecast": forecast_cfg,
                "checks": checks,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
