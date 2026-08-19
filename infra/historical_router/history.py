from __future__ import annotations

import json
import math
import os
import statistics
from datetime import datetime, timezone, timedelta
from typing import Any

from huggingface_hub import HfFileSystem


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def load_cost_history(
    bucket: str,
    *,
    max_records: int = 5000,
    recency_days: int = 90,
) -> list[dict[str, Any]]:
    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))
    paths = fs.glob(f"hf://buckets/{bucket}/runs/*/cost.json")
    if not paths:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=recency_days)
    rows: list[dict[str, Any]] = []

    for path in paths[-max_records:]:
        try:
            with fs.open(path, "r") as f:
                row = json.load(f)
        except Exception:
            continue

        observed = _parse_dt(row.get("observed_terminal_at"))
        if observed and observed < cutoff:
            continue

        rows.append(row)

    return rows


def candidate_key(row: dict[str, Any]) -> tuple[str, str]:
    provider = str(row.get("provider", "unknown"))
    gpu = (
        row.get("gpu_id")
        or row.get("gpu_name")
        or row.get("flavor")
        or row.get("resource_class")
        or "unknown"
    )
    return provider, str(gpu)


def normalized_runtime_per_unit(
    row: dict[str, Any],
    *,
    workload: str,
) -> float | None:
    runtime_hours = float(row.get("runtime_seconds", 0.0)) / 3600.0
    if runtime_hours <= 0:
        return None

    if workload == "teacher":
        units = row.get("input_audio_hours")
    elif workload == "student":
        units = row.get("epochs")
    else:
        units = 1.0

    try:
        units = float(units)
    except (TypeError, ValueError):
        return None

    if units <= 0:
        return None

    return runtime_hours / units


def robust_stats(values: list[float]) -> dict[str, float] | None:
    vals = [float(v) for v in values if math.isfinite(float(v)) and float(v) > 0]
    if not vals:
        return None

    med = statistics.median(vals)

    if len(vals) >= 2:
        deviations = [abs(x - med) for x in vals]
        mad = statistics.median(deviations)
    else:
        mad = 0.0

    return {
        "count": float(len(vals)),
        "median": float(med),
        "mad": float(mad),
    }
