from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from zoneinfo import ZoneInfo

from core import reservation_state


def load_schedule(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"version": 1, "dates": {}}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"version": 1, "dates": {}}


def scheduled_cost_usd(
    schedule: dict[str, Any],
    *,
    day: date,
    scope: str,
    fallback_cost_per_unit_usd: dict[str, float],
    fallback_cost_per_job_usd: dict[str, float] | None = None,
) -> float:
    row = (schedule.get("dates") or {}).get(day.isoformat()) or {}

    def workload_cost(workload: str) -> float:
        item = row.get(workload) or {}
        if item.get("expected_cost_usd") is not None:
            return max(0.0, float(item["expected_cost_usd"]))
        units = float(item.get("units", 0.0) or 0.0)
        jobs = float(item.get("jobs", 0.0) or 0.0)
        unit_cost = units * float(fallback_cost_per_unit_usd.get(workload, 0.0))
        job_cost = jobs * float((fallback_cost_per_job_usd or {}).get(workload, 0.0))
        return max(0.0, unit_cost + job_cost)

    if scope == "global":
        return workload_cost("teacher") + workload_cost("student")
    if scope.startswith("workload:"):
        return workload_cost(scope.split(":", 1)[1])
    return 0.0


def historical_daily_demand(
    events: list[dict[str, Any]],
    *,
    scope: str,
    now: datetime,
    tz_name: str,
    lookback_days: int,
) -> dict[date, float]:
    """Return settled/reserved committed GPU cost by reservation-local day."""
    local_now = now.astimezone(ZoneInfo(tz_name))
    start_day = local_now.date() - timedelta(days=lookback_days)
    out: dict[date, float] = defaultdict(float)

    # Zero-demand calendar days are observations too.
    d = start_day
    while d < local_now.date():
        out[d] += 0.0
        d += timedelta(days=1)

    for state in reservation_state(events).values():
        reservation = state.get("reservation")
        if not reservation:
            continue
        if scope not in reservation.get("scopes", []):
            continue

        day_text = (reservation.get("periods") or {}).get("daily")
        if not day_text:
            continue
        try:
            day = date.fromisoformat(day_text)
        except ValueError:
            continue
        if day < start_day or day >= local_now.date():
            continue

        settlement = state.get("settlement")
        release = state.get("release")
        if settlement:
            amount = float(settlement.get("actual_cost_usd", 0.0))
        elif release:
            amount = 0.0
        else:
            amount = float(reservation.get("reserved_cost_usd", 0.0))
        out[day] += max(0.0, amount)

    return dict(out)


def weekday_factors(
    daily_demand: dict[date, float],
    *,
    smoothing_days: float = 2.0,
) -> dict[int, float]:
    """Smoothed weekday mean / overall mean. Neutral factor is 1."""
    if not daily_demand:
        return {i: 1.0 for i in range(7)}

    total = sum(daily_demand.values())
    n_days = len(daily_demand)
    overall_mean = total / max(1, n_days)
    if overall_mean <= 0:
        return {i: 1.0 for i in range(7)}

    sums = defaultdict(float)
    counts = defaultdict(int)
    for d, amount in daily_demand.items():
        sums[d.weekday()] += amount
        counts[d.weekday()] += 1

    factors = {}
    prior_n = max(0.0, float(smoothing_days))
    for weekday in range(7):
        smoothed_mean = (
            sums[weekday] + prior_n * overall_mean
        ) / max(1e-9, counts[weekday] + prior_n)
        factors[weekday] = max(0.0, smoothed_mean / overall_mean)
    return factors


def _normalized_schedule_factors(
    schedule_costs: dict[date, float],
) -> dict[date, float]:
    if not schedule_costs:
        return {}
    values = list(schedule_costs.values())
    mean_value = sum(values) / len(values)
    if mean_value <= 0:
        return {d: 1.0 for d in schedule_costs}
    # Add a neutral prior equal to the mean so zero-plan days do not collapse.
    return {
        d: (cost + mean_value) / (2.0 * mean_value)
        for d, cost in schedule_costs.items()
    }


def remaining_day_weights(
    events: list[dict[str, Any]],
    *,
    scope: str,
    now: datetime,
    tz_name: str,
    forecast_cfg: dict[str, Any],
    schedule: dict[str, Any],
) -> list[dict[str, Any]]:
    local = now.astimezone(ZoneInfo(tz_name))
    last_day = (
        (local.replace(day=28) + timedelta(days=4)).replace(day=1)
        - timedelta(days=1)
    ).date()

    days = []
    d = local.date()
    while d <= last_day:
        days.append(d)
        d += timedelta(days=1)

    historical = historical_daily_demand(
        events,
        scope=scope,
        now=now,
        tz_name=tz_name,
        lookback_days=int(forecast_cfg["history_lookback_days"]),
    )
    weekday = weekday_factors(
        historical,
        smoothing_days=float(forecast_cfg["weekday_smoothing_days"]),
    )

    scheduled = {
        d: scheduled_cost_usd(
            schedule,
            day=d,
            scope=scope,
            fallback_cost_per_unit_usd=forecast_cfg[
                "fallback_cost_per_unit_usd"
            ],
            fallback_cost_per_job_usd=forecast_cfg.get(
                "fallback_cost_per_job_usd", {}
            ),
        )
        for d in days
    }
    schedule_factors = _normalized_schedule_factors(scheduled)

    weights_cfg = forecast_cfg["weights"]
    wb = max(0.0, float(weights_cfg.get("baseline", 0.0) or 0.0))
    wh = max(0.0, float(weights_cfg.get("weekday_history", 0.0) or 0.0))
    ws = max(0.0, float(weights_cfg.get("scheduled_jobs", 0.0) or 0.0))
    denom = wb + wh + ws
    if denom <= 0:
        wb, wh, ws, denom = 1.0, 0.0, 0.0, 1.0

    min_w = float(forecast_cfg.get("min_day_weight", 0.25))
    max_w = float(forecast_cfg.get("max_day_weight", 4.0))

    rows = []
    for d in days:
        h = weekday.get(d.weekday(), 1.0)
        sf = schedule_factors.get(d, 1.0)
        raw = (wb * 1.0 + wh * h + ws * sf) / denom
        weight = min(max_w, max(min_w, raw))
        rows.append(
            {
                "date": d.isoformat(),
                "weekday": d.weekday(),
                "weekday_history_factor": h,
                "scheduled_cost_usd": scheduled[d],
                "schedule_factor": sf,
                "demand_weight": weight,
            }
        )
    return rows
