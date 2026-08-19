#!/usr/bin/env python3
"""
Watch the provider-neutral HF Bucket completion markers, perform cleanup,
and write cost-accounting metadata.

Completion contract:
  runs/<job_id>/_SUCCESS.json
  runs/<job_id>/_FAILED.json

For HF Jobs, terminal Job state is also accepted because Jobs may execute
commands that do not use run_cloud_job.sh.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

from job_state import (
    CostRecord,
    exists,
    parse_iso,
    read_json,
    utc_now,
    write_json,
)
from provider_status import get_status
from cleanup import cleanup


HF_TERMINAL = {"COMPLETED", "CANCELED", "ERROR", "DELETED"}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--job-spec", required=True)
    p.add_argument("--provider", required=True)
    p.add_argument("--resource-id", required=True)
    p.add_argument("--quoted-price", required=True, type=float)
    p.add_argument("--launched-at", required=True)
    p.add_argument("--namespace")
    p.add_argument("--poll-seconds", type=int, default=30)
    p.add_argument("--timeout-seconds", type=int)
    args = p.parse_args()

    with open(args.job_spec, "r", encoding="utf-8") as f:
        spec = json.load(f)

    job_id = spec["job_id"]
    bucket = spec["hf_bucket"]
    timeout = args.timeout_seconds or int(spec.get("timeout_seconds", 14400))

    launched_at = parse_iso(args.launched_at)
    if launched_at is None:
        raise RuntimeError("Invalid launched-at")

    start_monotonic = time.monotonic()
    terminal_reason = None
    last_status = None

    while True:
        if exists(bucket, f"runs/{job_id}/_SUCCESS.json"):
            terminal_reason = "success_marker"
            break

        if exists(bucket, f"runs/{job_id}/_FAILED.json"):
            terminal_reason = "failed_marker"
            break

        try:
            last_status = get_status(
                args.provider,
                args.resource_id,
                namespace=args.namespace,
            )
        except Exception as exc:
            last_status = {
                "provider": args.provider,
                "resource_id": args.resource_id,
                "status_error": repr(exc),
            }

        if (
            args.provider == "hf_jobs"
            and last_status.get("status") in HF_TERMINAL
        ):
            terminal_reason = f"hf_terminal_{last_status['status'].lower()}"
            break

        if time.monotonic() - start_monotonic >= timeout:
            terminal_reason = "watchdog_timeout"
            break

        time.sleep(args.poll_seconds)

    observed_terminal_at = utc_now()

    # Provider reported price snapshot near terminal time when available.
    reported_price = None
    if last_status:
        try:
            reported_price = float(last_status.get("price_usd_per_hour"))
        except (TypeError, ValueError):
            reported_price = None

    runtime_seconds = max(
        0.0,
        (observed_terminal_at - launched_at).total_seconds(),
    )

    # HF Jobs exposes more accurate started_at/finished_at.
    if args.provider == "hf_jobs" and last_status:
        hf_started = parse_iso(last_status.get("started_at"))
        hf_finished = parse_iso(last_status.get("finished_at"))
        if hf_started and hf_finished:
            runtime_seconds = max(
                0.0,
                (hf_finished - hf_started).total_seconds(),
            )

    price = (
        reported_price
        if reported_price is not None
        else args.quoted_price
    )

    estimated_cost = runtime_seconds / 3600.0 * price

    accounting = spec.get("accounting") or {}
    audio_hours = accounting.get("input_audio_hours")
    epochs = accounting.get("epochs")
    samples = accounting.get("samples")

    record = CostRecord(
        schema_version="1.0",
        job_id=job_id,
        provider=args.provider,
        resource_id=args.resource_id,
        workload=spec["workload"],
        quoted_price_usd_per_hour=args.quoted_price,
        provider_reported_price_usd_per_hour=reported_price,
        launched_at=args.launched_at,
        observed_terminal_at=observed_terminal_at.isoformat(),
        runtime_seconds=runtime_seconds,
        estimated_cost_usd=estimated_cost,
        input_audio_hours=audio_hours,
        epochs=epochs,
        samples=samples,
        cost_per_input_audio_hour_usd=(
            estimated_cost / audio_hours
            if audio_hours not in (None, 0)
            else None
        ),
        cost_per_epoch_usd=(
            estimated_cost / epochs
            if epochs not in (None, 0)
            else None
        ),
        cost_per_1k_samples_usd=(
            estimated_cost / (samples / 1000.0)
            if samples not in (None, 0)
            else None
        ),
    )

    write_json(
        bucket,
        f"runs/{job_id}/cost.json",
        {
            **record.to_dict(),
            "terminal_reason": terminal_reason,
            "last_provider_status": last_status,
        },
    )

    # Cleanup after accounting snapshot. For HF Jobs, only cancel on timeout;
    # completed Jobs require no destructive action.
    cleanup_error = None
    try:
        if args.provider in {"runpod", "vast"}:
            cleanup(args.provider, args.resource_id, args.namespace)
        elif args.provider == "hf_jobs" and terminal_reason == "watchdog_timeout":
            cleanup(args.provider, args.resource_id, args.namespace)
    except Exception as exc:
        cleanup_error = repr(exc)

    write_json(
        bucket,
        f"runs/{job_id}/lifecycle.json",
        {
            "job_id": job_id,
            "provider": args.provider,
            "resource_id": args.resource_id,
            "terminal_reason": terminal_reason,
            "cleanup_error": cleanup_error,
            "accounted": True,
            "cleaned_up": cleanup_error is None,
        },
    )

    print(json.dumps(record.to_dict(), ensure_ascii=False, indent=2))

    if terminal_reason in {
        "failed_marker",
        "hf_terminal_error",
        "hf_terminal_canceled",
        "watchdog_timeout",
    }:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
