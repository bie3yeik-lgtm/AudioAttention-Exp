from __future__ import annotations

import math
from typing import Any


def candidate_key(candidate: dict[str, Any]) -> str:
    gpu = candidate.get("gpu_id") or candidate.get("flavor") or "unknown"
    return f"{candidate['provider']}::{gpu}"


def uncertainty_fraction(
    candidate: dict[str, Any],
    paired: dict[str, float] | None,
    *,
    paired_weight: float,
    saturation_observations: float,
    minimum_fraction: float,
    cold_start_fraction: float,
) -> tuple[float, float]:
    """
    Convert historical + paired evidence into a bounded uncertainty fraction.

    This is intentionally simple and auditable. It is not a Bayesian posterior.
    """
    history_count = float(candidate.get("history_count", 0) or 0)
    paired_count = float((paired or {}).get("paired_observations", 0) or 0)

    effective_n = history_count + paired_count * paired_weight

    if effective_n <= 0:
        return cold_start_fraction, 0.0

    # Evidence uncertainty falls approximately as 1/sqrt(n).
    evidence_fraction = 1.0 / math.sqrt(effective_n + 1.0)

    # Historical MAD contributes empirical variability.
    runtime = float(candidate.get("runtime_hours_per_unit", 0) or 0)
    mad = candidate.get("mad")
    if mad is None or runtime <= 0:
        variability_fraction = minimum_fraction
    else:
        variability_fraction = max(
            minimum_fraction,
            min(1.0, float(mad) / runtime),
        )

    fraction = max(
        minimum_fraction,
        min(
            cold_start_fraction,
            variability_fraction * evidence_fraction
            + minimum_fraction,
        ),
    )

    saturation = min(1.0, effective_n / saturation_observations)
    return fraction, saturation


def bandit_score(
    candidate: dict[str, Any],
    *,
    uncertainty_fraction_value: float,
    beta: float,
) -> dict[str, Any]:
    """
    Cost minimization uses an optimistic Lower Confidence Bound:

        LCB = predicted_cost - beta * uncertainty

    Lower score wins.
    """
    predicted = float(candidate["risk_adjusted_total_cost_usd"])
    uncertainty_usd = predicted * uncertainty_fraction_value
    exploration_bonus = beta * uncertainty_usd
    score = max(0.0, predicted - exploration_bonus)

    return {
        **candidate,
        "bandit_uncertainty_fraction": uncertainty_fraction_value,
        "bandit_uncertainty_usd": uncertainty_usd,
        "bandit_exploration_bonus_usd": exploration_bonus,
        "bandit_lcb_score_usd": score,
    }


def is_safe_alternative(
    candidate: dict[str, Any],
    greedy: dict[str, Any],
    *,
    max_extra_cost_usd: float,
    max_relative_premium: float,
) -> tuple[bool, str]:
    candidate_cost = float(candidate["predicted_total_cost_usd"])
    greedy_cost = float(greedy["predicted_total_cost_usd"])

    extra = max(0.0, candidate_cost - greedy_cost)
    relative = extra / greedy_cost if greedy_cost > 0 else float("inf")

    if extra > max_extra_cost_usd:
        return False, "absolute_cost_guard"

    if relative > max_relative_premium:
        return False, "relative_cost_guard"

    return True, "safe"
