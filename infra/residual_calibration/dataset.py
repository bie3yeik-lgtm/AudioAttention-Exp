from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from huggingface_hub import HfFileSystem


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _load_json(fs: HfFileSystem, path: str) -> dict[str, Any] | None:
    try:
        with fs.open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def load_residual_frame(
    bucket: str,
    *,
    recency_days: int,
    max_records: int,
) -> pd.DataFrame:
    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))

    eval_paths = fs.glob(
        f"hf://buckets/{bucket}/runs/*/contextual-evaluation.json"
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=recency_days)
    rows = []

    for eval_path in eval_paths[-max_records:]:
        ev = _load_json(fs, eval_path)
        if not ev or not ev.get("evaluable"):
            continue

        job_id = ev["job_id"]

        cost_path = f"hf://buckets/{bucket}/runs/{job_id}/cost.json"
        decision_path = (
            f"hf://buckets/{bucket}/runs/{job_id}/contextual-decision.json"
        )

        cost = _load_json(fs, cost_path)
        decision = _load_json(fs, decision_path)

        if not cost or not decision:
            continue

        observed = _parse_dt(cost.get("observed_terminal_at"))
        if observed and observed < cutoff:
            continue

        contextual = ev.get("contextual") or {}
        if not contextual.get("same_route"):
            # Residual labels are only trustworthy when the contextual
            # prediction corresponds to the route that actually executed.
            continue

        ctx = cost.get("job_context") or {}
        rec = decision.get("contextual_recommendation") or {}

        cost_ape = contextual.get("cost_ape")
        runtime_ape = contextual.get("runtime_ape")

        if cost_ape is None or runtime_ape is None:
            continue

        rows.append(
            {
                "job_id": job_id,
                "observed_terminal_at": cost.get("observed_terminal_at"),

                "workload": cost.get("workload", "unknown"),
                "provider": cost.get("provider", "unknown"),
                "gpu_id": str(
                    cost.get("gpu_id")
                    or cost.get("flavor")
                    or "unknown"
                ),

                "predicted_cost_usd": rec.get(
                    "contextual_blended_total_cost_usd",
                    contextual.get("predicted_cost_usd"),
                ),
                "predicted_runtime_seconds": rec.get(
                    "predicted_runtime_seconds",
                    contextual.get("predicted_runtime_seconds"),
                ),
                "quoted_price_usd_per_hour": cost.get(
                    "quoted_price_usd_per_hour"
                ),

                "input_audio_hours": cost.get("input_audio_hours"),
                "epochs": cost.get("epochs"),
                "samples": cost.get("samples"),

                "audio_duration_hours": ctx.get("audio_duration_hours"),
                "sample_count": ctx.get("sample_count"),
                "dataset_size_bytes": ctx.get("dataset_size_bytes"),
                "batch_size": ctx.get("batch_size"),
                "sequence_length": ctx.get("sequence_length"),

                "model_revision": ctx.get("model_revision"),
                "prompt_revision": ctx.get("prompt_revision"),
                "dataset_revision": ctx.get("dataset_revision"),
                "cache_state": ctx.get("cache_state"),
                "precision": ctx.get("precision"),
                "gpu_architecture": ctx.get("gpu_architecture"),
                "framework_revision": ctx.get("framework_revision"),
                "container_revision": ctx.get("container_revision"),
                "feature_schema_revision": ctx.get(
                    "feature_schema_revision"
                ),

                "contextual_cost_ape": float(cost_ape),
                "contextual_runtime_ape": float(runtime_ape),
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    if "observed_terminal_at" in df.columns:
        df = df.sort_values("observed_terminal_at")
    return df.reset_index(drop=True)
