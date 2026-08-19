from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
