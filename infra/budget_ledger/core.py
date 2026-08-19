from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import calendar
from typing import Any
from zoneinfo import ZoneInfo


TERMINAL_TYPES = {"settlement", "release"}


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def period_keys(now: datetime, tz_name: str) -> dict[str, str]:
    local = now.astimezone(ZoneInfo(tz_name))
    iso_year, iso_week, _ = local.isocalendar()
    return {
        "daily": local.strftime("%Y-%m-%d"),
        "weekly": f"{iso_year}-W{iso_week:02d}",
        "monthly": local.strftime("%Y-%m"),
    }


def scope_names(workload: str) -> list[str]:
    return ["global", f"workload:{workload}"]


def reservation_state(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Fold append-only events into one state per reservation/job."""
    state: dict[str, dict[str, Any]] = {}
    for event in sorted(events, key=lambda x: x.get("created_at", "")):
        rid = str(event.get("reservation_id") or event.get("job_id") or "")
        if not rid:
            continue
        s = state.setdefault(
            rid,
            {
                "reservation": None,
                "settlement": None,
                "release": None,
            },
        )
        et = event.get("event_type")
        if et in s:
            s[et] = event
    return state


def usage_for_period(
    events: list[dict[str, Any]],
    *,
    period_type: str,
    period_key: str,
    scope: str,
) -> dict[str, float]:
    spent = 0.0
    reserved = 0.0
    states = reservation_state(events)

    for s in states.values():
        reservation = s.get("reservation")
        if not reservation:
            continue
        if reservation.get("periods", {}).get(period_type) != period_key:
            continue
        if scope not in reservation.get("scopes", []):
            continue

        settlement = s.get("settlement")
        release = s.get("release")
        if settlement:
            spent += float(settlement.get("actual_cost_usd", 0.0))
        elif release:
            continue
        else:
            reserved += float(reservation.get("reserved_cost_usd", 0.0))

    return {
        "spent_usd": spent,
        "reserved_usd": reserved,
        "committed_usd": spent + reserved,
    }


def check_limits(
    events: list[dict[str, Any]],
    *,
    workload: str,
    amount_usd: float,
    periods: dict[str, str],
    limits: dict[str, dict[str, float | None]],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for scope in scope_names(workload):
        scope_limits = limits.get(scope, {})
        for period_type in ("daily", "weekly", "monthly"):
            cap = scope_limits.get(period_type)
            if cap is None:
                continue
            usage = usage_for_period(
                events,
                period_type=period_type,
                period_key=periods[period_type],
                scope=scope,
            )
            remaining = float(cap) - usage["committed_usd"]
            checks.append(
                {
                    "scope": scope,
                    "period_type": period_type,
                    "period_key": periods[period_type],
                    "limit_usd": float(cap),
                    **usage,
                    "requested_usd": float(amount_usd),
                    "remaining_before_usd": remaining,
                    "allowed": float(amount_usd) <= remaining + 1e-9,
                }
            )
    return checks


def open_reservations(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for s in reservation_state(events).values():
        if s.get("reservation") and not s.get("settlement") and not s.get("release"):
            out.append(s["reservation"])
    return out



def pacing_checks(
    events: list[dict[str, Any]],
    *,
    workload: str,
    amount_usd: float,
    now: datetime,
    tz_name: str,
    limits: dict[str, dict[str, float | None]],
    pacing: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compute daily pacing guards from each scope's monthly cap.

    The allowance is recalculated every reservation from the budget that was
    available at the start of the current local day:

        (monthly_cap - committed_before_today) / remaining_days_in_month

    This naturally carries unused budget forward. Current-day committed spend
    is then subtracted from today's allowance.
    """
    if not pacing.get("enabled", True):
        return []

    local = now.astimezone(ZoneInfo(tz_name))
    days_in_month = calendar.monthrange(local.year, local.month)[1]
    remaining_days = days_in_month - local.day + 1
    periods = period_keys(now, tz_name)
    multiplier = float(pacing.get("pace_multiplier", 1.0))
    min_daily = float(pacing.get("min_daily_allowance_usd", 0.0) or 0.0)
    max_daily = pacing.get("max_daily_allowance_usd")
    max_daily = None if max_daily is None else float(max_daily)
    mode = str(pacing.get("mode", "enforce"))

    checks: list[dict[str, Any]] = []
    for scope in scope_names(workload):
        monthly_cap = limits.get(scope, {}).get("monthly")
        if monthly_cap is None:
            continue

        monthly = usage_for_period(
            events,
            period_type="monthly",
            period_key=periods["monthly"],
            scope=scope,
        )
        daily = usage_for_period(
            events,
            period_type="daily",
            period_key=periods["daily"],
            scope=scope,
        )

        committed_before_today = max(
            0.0, monthly["committed_usd"] - daily["committed_usd"]
        )
        month_available_at_day_start = max(
            0.0, float(monthly_cap) - committed_before_today
        )
        base_allowance = month_available_at_day_start / remaining_days
        allowance = max(min_daily, base_allowance * multiplier)
        if max_daily is not None:
            allowance = min(allowance, max_daily)
        allowance = min(allowance, month_available_at_day_start)
        available_today = max(0.0, allowance - daily["committed_usd"])
        would_fit = float(amount_usd) <= available_today + 1e-9

        checks.append(
            {
                "scope": scope,
                "mode": mode,
                "period_key": periods["daily"],
                "monthly_period_key": periods["monthly"],
                "monthly_limit_usd": float(monthly_cap),
                "remaining_days_in_month": remaining_days,
                "monthly_committed_usd": monthly["committed_usd"],
                "daily_committed_usd": daily["committed_usd"],
                "committed_before_today_usd": committed_before_today,
                "month_available_at_day_start_usd": month_available_at_day_start,
                "base_daily_allowance_usd": base_allowance,
                "pace_multiplier": multiplier,
                "daily_allowance_usd": allowance,
                "available_today_usd": available_today,
                "requested_usd": float(amount_usd),
                "would_fit": would_fit,
                "allowed": would_fit if mode == "enforce" else True,
            }
        )
    return checks


def forecast_aware_pacing_checks(
    events: list[dict[str, Any]],
    *,
    workload: str,
    amount_usd: float,
    now: datetime,
    tz_name: str,
    limits: dict[str, dict[str, float | None]],
    pacing: dict[str, Any],
    forecast_cfg: dict[str, Any],
    schedule: dict[str, Any],
) -> list[dict[str, Any]]:
    """Demand-weighted monthly pacing.

    Falls back to ordinary remaining-days pacing when forecast is disabled.
    """
    if not pacing.get("enabled", True):
        return []

    if not forecast_cfg.get("enabled", True):
        return pacing_checks(
            events,
            workload=workload,
            amount_usd=amount_usd,
            now=now,
            tz_name=tz_name,
            limits=limits,
            pacing=pacing,
        )

    from forecast import remaining_day_weights

    local = now.astimezone(ZoneInfo(tz_name))
    periods = period_keys(now, tz_name)
    multiplier = float(pacing.get("pace_multiplier", 1.0))
    min_daily = float(pacing.get("min_daily_allowance_usd", 0.0) or 0.0)
    max_daily = pacing.get("max_daily_allowance_usd")
    max_daily = None if max_daily is None else float(max_daily)
    mode = str(pacing.get("mode", "enforce"))

    checks: list[dict[str, Any]] = []
    for scope in scope_names(workload):
        monthly_cap = limits.get(scope, {}).get("monthly")
        if monthly_cap is None:
            continue

        monthly = usage_for_period(
            events,
            period_type="monthly",
            period_key=periods["monthly"],
            scope=scope,
        )
        daily = usage_for_period(
            events,
            period_type="daily",
            period_key=periods["daily"],
            scope=scope,
        )

        committed_before_today = max(
            0.0, monthly["committed_usd"] - daily["committed_usd"]
        )
        month_available_at_day_start = max(
            0.0, float(monthly_cap) - committed_before_today
        )

        weights = remaining_day_weights(
            events,
            scope=scope,
            now=now,
            tz_name=tz_name,
            forecast_cfg=forecast_cfg,
            schedule=schedule,
        )
        total_weight = sum(float(x["demand_weight"]) for x in weights)
        today = next(
            (x for x in weights if x["date"] == local.date().isoformat()),
            None,
        )
        today_weight = float(today["demand_weight"]) if today else 1.0

        if total_weight <= 0:
            base_allowance = month_available_at_day_start / max(1, len(weights))
        else:
            base_allowance = (
                month_available_at_day_start * today_weight / total_weight
            )

        allowance = max(min_daily, base_allowance * multiplier)
        if max_daily is not None:
            allowance = min(allowance, max_daily)
        allowance = min(allowance, month_available_at_day_start)

        available_today = max(0.0, allowance - daily["committed_usd"])
        would_fit = float(amount_usd) <= available_today + 1e-9

        checks.append(
            {
                "scope": scope,
                "mode": mode,
                "strategy": "forecast_aware",
                "period_key": periods["daily"],
                "monthly_period_key": periods["monthly"],
                "monthly_limit_usd": float(monthly_cap),
                "monthly_committed_usd": monthly["committed_usd"],
                "daily_committed_usd": daily["committed_usd"],
                "committed_before_today_usd": committed_before_today,
                "month_available_at_day_start_usd": month_available_at_day_start,
                "remaining_days_in_month": len(weights),
                "today_demand_weight": today_weight,
                "remaining_demand_weight": total_weight,
                "weekday_history_factor": (
                    today.get("weekday_history_factor") if today else None
                ),
                "scheduled_cost_usd": (
                    today.get("scheduled_cost_usd") if today else 0.0
                ),
                "schedule_factor": (
                    today.get("schedule_factor") if today else None
                ),
                "base_daily_allowance_usd": base_allowance,
                "pace_multiplier": multiplier,
                "daily_allowance_usd": allowance,
                "available_today_usd": available_today,
                "requested_usd": float(amount_usd),
                "would_fit": would_fit,
                "allowed": would_fit if mode == "enforce" else True,
                "remaining_day_weights": weights,
            }
        )

    return checks
