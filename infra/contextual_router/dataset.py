from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from huggingface_hub import HfFileSystem

from features import flatten_cost_record


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def load_training_frame(
    bucket: str,
    *,
    recency_days: int,
    max_records: int,
) -> pd.DataFrame:
    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))
    paths = fs.glob(f"hf://buckets/{bucket}/runs/*/cost.json")

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

        flat = flatten_cost_record(row)

        try:
            runtime = float(flat["runtime_seconds"])
            cost = float(flat["estimated_cost_usd"])
        except (TypeError, ValueError):
            continue

        if runtime <= 0 or cost < 0:
            continue

        rows.append(flat)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    if "observed_terminal_at" in df.columns:
        df = df.sort_values("observed_terminal_at")

    return df.reset_index(drop=True)
