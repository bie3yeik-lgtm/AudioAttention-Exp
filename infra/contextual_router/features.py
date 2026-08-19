from __future__ import annotations

from typing import Any

import pandas as pd


DEFAULT_CATEGORICAL = [
    "workload",
    "provider",
    "gpu_id",
    "model_revision",
    "prompt_revision",
    "dataset_revision",
    "cache_state",
    "precision",
    "gpu_architecture",
    "framework_revision",
    "container_revision",
    "feature_schema_revision",
]

DEFAULT_NUMERICAL = [
    "quoted_price_usd_per_hour",
    "provider_reported_price_usd_per_hour",
    "input_audio_hours",
    "epochs",
    "samples",
    "audio_duration_hours",
    "sample_count",
    "dataset_size_bytes",
    "batch_size",
    "sequence_length",
    "teacher_prompt_tokens_estimate",
]


def flatten_cost_record(row: dict[str, Any]) -> dict[str, Any]:
    ctx = row.get("job_context") or {}

    gpu_id = (
        row.get("gpu_id")
        or row.get("flavor")
        or ctx.get("gpu_id")
        or "unknown"
    )

    flat = {
        "job_id": row.get("job_id"),
        "workload": row.get("workload", "unknown"),
        "provider": row.get("provider", "unknown"),
        "gpu_id": str(gpu_id),

        "quoted_price_usd_per_hour": row.get("quoted_price_usd_per_hour"),
        "provider_reported_price_usd_per_hour": row.get(
            "provider_reported_price_usd_per_hour"
        ),

        "input_audio_hours": row.get("input_audio_hours"),
        "epochs": row.get("epochs"),
        "samples": row.get("samples"),

        "runtime_seconds": row.get("runtime_seconds"),
        "estimated_cost_usd": row.get("estimated_cost_usd"),

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
        "feature_schema_revision": ctx.get("feature_schema_revision"),

        "teacher_prompt_tokens_estimate": ctx.get(
            "teacher_prompt_tokens_estimate"
        ),

        "observed_terminal_at": row.get("observed_terminal_at"),
    }

    return flat


def normalize_frame(
    df: pd.DataFrame,
    *,
    categorical: list[str],
    numerical: list[str],
) -> pd.DataFrame:
    df = df.copy()

    for col in categorical:
        if col not in df.columns:
            df[col] = "unknown"
        df[col] = df[col].fillna("unknown").astype(str)

    for col in numerical:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df


def candidate_feature_row(
    *,
    workload: str,
    provider: str,
    gpu_id: str,
    price_usd_per_hour: float,
    accounting: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "workload": workload,
        "provider": provider,
        "gpu_id": gpu_id,
        "quoted_price_usd_per_hour": price_usd_per_hour,
        "provider_reported_price_usd_per_hour": price_usd_per_hour,
        "input_audio_hours": accounting.get("input_audio_hours"),
        "epochs": accounting.get("epochs"),
        "samples": accounting.get("samples"),
        **{
            key: context.get(key)
            for key in [
                "audio_duration_hours",
                "sample_count",
                "dataset_size_bytes",
                "batch_size",
                "sequence_length",
                "model_revision",
                "prompt_revision",
                "dataset_revision",
                "cache_state",
                "precision",
                "gpu_architecture",
                "framework_revision",
                "container_revision",
                "feature_schema_revision",
                "teacher_prompt_tokens_estimate",
            ]
        },
    }
