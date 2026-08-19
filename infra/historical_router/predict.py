from __future__ import annotations

from collections import defaultdict
from typing import Any

from .history import candidate_key, normalized_runtime_per_unit, robust_stats


def build_models(
    rows: list[dict[str, Any]],
    *,
    workload: str,
) -> dict[tuple[str, str], dict[str, float]]:
    values: dict[tuple[str, str], list[float]] = defaultdict(list)

    for row in rows:
        if row.get("workload") != workload:
            continue

        runtime = normalized_runtime_per_unit(row, workload=workload)
        if runtime is None:
            continue

        values[candidate_key(row)].append(runtime)

    result = {}
    for key, samples in values.items():
        stats = robust_stats(samples)
        if stats:
            result[key] = stats
    return result


def predict_runtime_hours_per_unit(
    *,
    candidate: dict[str, Any],
    models: dict[tuple[str, str], dict[str, float]],
    global_prior: float,
    min_samples: int,
    prior_weight: float,
    cold_start_multiplier: float,
) -> dict[str, Any]:
    provider = str(candidate["provider"])
    gpu = str(
        candidate.get("gpu_id")
        or candidate.get("gpu_name")
        or candidate.get("flavor")
        or "unknown"
    )

    stats = models.get((provider, gpu))

    if not stats:
        return {
            "runtime_hours_per_unit": global_prior * cold_start_multiplier,
            "history_count": 0,
            "mad": None,
            "source": "cold_start_prior",
        }

    count = int(stats["count"])
    median = stats["median"]

    # Shrink sparse candidates toward the workload prior.
    effective_weight = min(count, min_samples)
    numerator = median * effective_weight + global_prior * prior_weight
    denominator = effective_weight + prior_weight

    estimate = numerator / denominator

    return {
        "runtime_hours_per_unit": estimate,
        "history_count": count,
        "mad": stats["mad"],
        "source": "historical_shrunk_median",
    }


def predict_total_cost(
    *,
    candidate: dict[str, Any],
    runtime_prediction: dict[str, Any],
    units: float,
    uncertainty_penalty: float,
) -> dict[str, Any]:
    price = float(candidate["price_usd_per_hour"])
    runtime_per_unit = float(runtime_prediction["runtime_hours_per_unit"])

    runtime_hours = runtime_per_unit * units
    base_cost = runtime_hours * price

    count = int(runtime_prediction["history_count"])
    mad = runtime_prediction.get("mad")

    penalty = 0.0
    if count == 0:
        penalty = uncertainty_penalty
    elif mad is not None and runtime_per_unit > 0:
        penalty = min(
            uncertainty_penalty,
            float(mad) / runtime_per_unit * uncertainty_penalty,
        )

    risk_adjusted_cost = base_cost * (1.0 + penalty)

    return {
        **candidate,
        **runtime_prediction,
        "units": units,
        "predicted_runtime_hours": runtime_hours,
        "predicted_total_cost_usd": base_cost,
        "risk_adjusted_total_cost_usd": risk_adjusted_cost,
        "uncertainty_penalty_fraction": penalty,
    }
