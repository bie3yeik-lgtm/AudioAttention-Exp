from __future__ import annotations

import yaml
from typing import Any

from model import ResidualCalibrationModel


def load_config(path: str = "configs/residual-calibration.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def feature_row_from_candidate(
    candidate: dict[str, Any],
    *,
    workload: str,
    context: dict[str, Any],
    accounting: dict[str, Any],
) -> dict[str, Any]:
    return {
        "workload": workload,
        "provider": candidate["provider"],
        "gpu_id": candidate.get("gpu_id", "unknown"),

        "predicted_cost_usd": candidate.get(
            "contextual_blended_total_cost_usd",
            candidate.get("predicted_total_cost_usd", 0.0),
        ),
        "predicted_runtime_seconds": candidate.get(
            "predicted_runtime_seconds",
            float(candidate.get("predicted_runtime_hours", 0.0)) * 3600.0,
        ),
        "quoted_price_usd_per_hour": candidate.get(
            "price_usd_per_hour", 0.0
        ),

        "input_audio_hours": accounting.get("input_audio_hours"),
        "epochs": accounting.get("epochs"),
        "samples": accounting.get("samples"),

        "audio_duration_hours": context.get("audio_duration_hours"),
        "sample_count": context.get("sample_count"),
        "dataset_size_bytes": context.get("dataset_size_bytes"),
        "batch_size": context.get("batch_size"),
        "sequence_length": context.get("sequence_length"),

        "model_revision": context.get("model_revision"),
        "prompt_revision": context.get("prompt_revision"),
        "dataset_revision": context.get("dataset_revision"),
        "cache_state": context.get("cache_state"),
        "precision": context.get("precision"),
        "gpu_architecture": context.get("gpu_architecture"),
        "framework_revision": context.get("framework_revision"),
        "container_revision": context.get("container_revision"),
        "feature_schema_revision": context.get(
            "feature_schema_revision"
        ),
    }


def calibrate_candidates(
    candidates: list[dict[str, Any]],
    *,
    bucket: str,
    workload: str,
    context: dict[str, Any],
    accounting: dict[str, Any],
    config_path: str = "configs/residual-calibration.yaml",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cfg = load_config(config_path)
    ccfg = cfg["confidence"]

    fallback = float(ccfg["fallback_uncertainty_fraction"])
    floor = float(ccfg["min_uncertainty_fraction"])
    ceiling = float(ccfg["max_uncertainty_fraction"])
    multiplier = float(ccfg["safety_multiplier"])

    try:
        model = ResidualCalibrationModel.load_latest(
            bucket,
            config_path=config_path,
        )
        rows = [
            feature_row_from_candidate(
                c,
                workload=workload,
                context=context,
                accounting=accounting,
            )
            for c in candidates
        ]
        predictions = model.predict(rows)
        source = "residual_calibration_model"
        metadata = model.metadata
    except Exception as exc:
        predictions = [
            {
                "predicted_cost_ape": fallback,
                "predicted_runtime_ape": fallback,
            }
            for _ in candidates
        ]
        source = "fallback_uncertainty"
        metadata = {"load_error": repr(exc)}

    out = []

    for candidate, pred in zip(candidates, predictions):
        raw_fraction = float(pred["predicted_cost_ape"]) * multiplier

        calibrated_fraction = max(
            floor,
            min(ceiling, raw_fraction),
        )

        c = dict(candidate)
        c["calibrated_cost_ape"] = float(
            pred["predicted_cost_ape"]
        )
        c["calibrated_runtime_ape"] = float(
            pred["predicted_runtime_ape"]
        )
        c["calibrated_uncertainty_fraction"] = calibrated_fraction
        c["calibration_source"] = source

        predicted_cost = float(
            c.get(
                "contextual_blended_total_cost_usd",
                c.get("risk_adjusted_total_cost_usd", 0.0),
            )
        )

        c["calibrated_uncertainty_usd"] = (
            predicted_cost * calibrated_fraction
        )

        out.append(c)

    return out, {
        "source": source,
        "metadata": metadata,
    }
