from __future__ import annotations

from typing import Any


class BudgetError(RuntimeError):
    pass


def parse_budget(
    job_spec: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    raw = job_spec.get("budget") or {}

    mode = raw.get("mode", defaults["mode"])
    max_cost = raw.get("max_cost_usd")
    confidence = raw.get(
        "target_confidence",
        defaults["target_confidence"],
    )
    penalty = raw.get(
        "soft_penalty_multiplier",
        defaults["soft_penalty_multiplier"],
    )

    if mode in {"soft_budget", "hard_budget"} and max_cost is None:
        raise BudgetError(
            f"{mode} requires budget.max_cost_usd"
        )

    return {
        "mode": mode,
        "max_cost_usd": (
            float(max_cost) if max_cost is not None else None
        ),
        "target_confidence": float(confidence),
        "soft_penalty_multiplier": float(penalty),
    }


def expected_cost(candidate: dict[str, Any]) -> float:
    for key in (
        "contextual_blended_total_cost_usd",
        "risk_adjusted_total_cost_usd",
        "predicted_total_cost_usd",
    ):
        if candidate.get(key) is not None:
            return float(candidate[key])
    raise BudgetError("Candidate has no predicted cost")


def upper_cost(candidate: dict[str, Any]) -> float | None:
    if candidate.get("conformal_ucb_cost_usd") is not None:
        return float(candidate["conformal_ucb_cost_usd"])

    conformal = candidate.get("conformal") or {}
    if conformal.get("cost_upper_usd") is not None:
        return float(conformal["cost_upper_usd"])

    return None


def lower_cost(candidate: dict[str, Any]) -> float | None:
    if candidate.get("conformal_lcb_cost_usd") is not None:
        return float(candidate["conformal_lcb_cost_usd"])

    conformal = candidate.get("conformal") or {}
    if conformal.get("cost_lower_usd") is not None:
        return float(conformal["cost_lower_usd"])

    return None


def apply_budget_policy(
    candidates: list[dict[str, Any]],
    *,
    budget: dict[str, Any],
    tolerance_usd: float,
    require_conformal_for_hard: bool,
    soft_use_upper_excess: bool,
) -> list[dict[str, Any]]:
    out = []

    mode = budget["mode"]
    cap = budget["max_cost_usd"]
    penalty_mult = budget["soft_penalty_multiplier"]

    for candidate in candidates:
        c = dict(candidate)
        exp = expected_cost(c)
        upper = upper_cost(c)
        lower = lower_cost(c)

        c["budget_mode"] = mode
        c["budget_max_cost_usd"] = cap
        c["budget_expected_cost_usd"] = exp
        c["budget_lower_cost_usd"] = lower
        c["budget_upper_cost_usd"] = upper

        if mode == "unbounded":
            c["budget_feasible"] = True
            c["budget_score_usd"] = exp
            c["budget_reason"] = "unbounded"
            out.append(c)
            continue

        if mode == "hard_budget":
            if upper is None and require_conformal_for_hard:
                c["budget_feasible"] = False
                c["budget_score_usd"] = float("inf")
                c["budget_reason"] = "missing_conformal_upper_bound"
                out.append(c)
                continue

            check_cost = upper if upper is not None else exp
            feasible = check_cost <= float(cap) + tolerance_usd

            c["budget_feasible"] = feasible
            c["budget_score_usd"] = exp if feasible else float("inf")
            c["budget_reason"] = (
                "within_hard_budget"
                if feasible
                else "hard_budget_exceeded"
            )
            c["budget_margin_usd"] = float(cap) - check_cost
            out.append(c)
            continue

        if mode == "soft_budget":
            if soft_use_upper_excess and upper is not None:
                risk_cost = upper
                source = "upper_bound"
            else:
                risk_cost = exp
                source = "expected_cost"

            excess = max(0.0, risk_cost - float(cap))
            score = exp + penalty_mult * excess

            c["budget_feasible"] = True
            c["budget_score_usd"] = score
            c["budget_excess_usd"] = excess
            c["budget_reason"] = f"soft_budget_{source}"
            out.append(c)
            continue

        raise BudgetError(f"Unknown budget mode: {mode}")

    return out
