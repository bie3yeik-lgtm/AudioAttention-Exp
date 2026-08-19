from datetime import datetime, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "infra" / "budget_ledger"))

from core import check_limits, pacing_checks, period_keys, reservation_state, usage_for_period


def reservation(job_id, amount, periods, workload="teacher", created="2026-08-20T00:00:00+00:00"):
    return {
        "event_type": "reservation",
        "reservation_id": job_id,
        "job_id": job_id,
        "workload": workload,
        "reserved_cost_usd": amount,
        "periods": periods,
        "scopes": ["global", f"workload:{workload}"],
        "created_at": created,
    }


def test_open_reservation_counts_as_committed():
    periods = {"daily": "2026-08-20", "weekly": "2026-W34", "monthly": "2026-08"}
    events = [reservation("a", 2.0, periods)]
    u = usage_for_period(events, period_type="monthly", period_key="2026-08", scope="global")
    assert u == {"spent_usd": 0.0, "reserved_usd": 2.0, "committed_usd": 2.0}


def test_settlement_replaces_reservation_with_actual_cost():
    periods = {"daily": "2026-08-20", "weekly": "2026-W34", "monthly": "2026-08"}
    events = [
        reservation("a", 2.0, periods),
        {"event_type": "settlement", "reservation_id": "a", "actual_cost_usd": 1.25, "created_at": "2026-08-20T01:00:00+00:00"},
    ]
    u = usage_for_period(events, period_type="monthly", period_key="2026-08", scope="global")
    assert u == {"spent_usd": 1.25, "reserved_usd": 0.0, "committed_usd": 1.25}


def test_release_frees_reservation():
    periods = {"daily": "2026-08-20", "weekly": "2026-W34", "monthly": "2026-08"}
    events = [
        reservation("a", 2.0, periods),
        {"event_type": "release", "reservation_id": "a", "created_at": "2026-08-20T01:00:00+00:00"},
    ]
    u = usage_for_period(events, period_type="monthly", period_key="2026-08", scope="global")
    assert u["committed_usd"] == 0.0


def test_budget_denies_oversubscription():
    periods = {"daily": "2026-08-20", "weekly": "2026-W34", "monthly": "2026-08"}
    events = [reservation("a", 8.0, periods)]
    checks = check_limits(
        events,
        workload="teacher",
        amount_usd=3.0,
        periods=periods,
        limits={"global": {"monthly": 10.0}, "workload:teacher": {"monthly": 9.0}},
    )
    assert checks
    assert all(not c["allowed"] for c in checks)


def test_period_keys_jst():
    p = period_keys(datetime(2026, 8, 19, 16, 30, tzinfo=timezone.utc), "Asia/Tokyo")
    assert p["daily"] == "2026-08-20"
    assert p["monthly"] == "2026-08"



def test_pacing_distributes_remaining_month_budget_over_remaining_days():
    now = datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc)  # Aug 20 JST as well
    periods = period_keys(now, "Asia/Tokyo")
    events = []
    checks = pacing_checks(
        events,
        workload="teacher",
        amount_usd=1.0,
        now=now,
        tz_name="Asia/Tokyo",
        limits={"global": {"monthly": 12.0}, "workload:teacher": {"monthly": None}},
        pacing={"enabled": True, "mode": "enforce", "pace_multiplier": 1.0, "min_daily_allowance_usd": 0.0, "max_daily_allowance_usd": None},
    )
    # Aug 20 -> 12 calendar days including today. $12 / 12 = $1/day.
    assert checks[0]["remaining_days_in_month"] == 12
    assert checks[0]["daily_allowance_usd"] == 1.0
    assert checks[0]["allowed"] is True


def test_pacing_carries_underused_budget_forward():
    now = datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc)
    periods = period_keys(now, "Asia/Tokyo")
    # Only $4 committed before today from a $16 monthly budget.
    prior_periods = dict(periods)
    prior_periods["daily"] = "2026-08-19"
    events = [reservation("prior", 4.0, prior_periods)]
    checks = pacing_checks(
        events,
        workload="teacher",
        amount_usd=1.0,
        now=now,
        tz_name="Asia/Tokyo",
        limits={"global": {"monthly": 16.0}, "workload:teacher": {"monthly": None}},
        pacing={"enabled": True, "mode": "enforce", "pace_multiplier": 1.0, "min_daily_allowance_usd": 0.0, "max_daily_allowance_usd": None},
    )
    # ($16-$4) / 12 days = $1 available today.
    assert checks[0]["daily_allowance_usd"] == 1.0
    assert checks[0]["allowed"] is True


def test_pacing_counts_today_commitment_against_allowance():
    now = datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc)
    periods = period_keys(now, "Asia/Tokyo")
    events = [reservation("today", 0.75, periods)]
    checks = pacing_checks(
        events,
        workload="teacher",
        amount_usd=0.30,
        now=now,
        tz_name="Asia/Tokyo",
        limits={"global": {"monthly": 12.0}, "workload:teacher": {"monthly": None}},
        pacing={"enabled": True, "mode": "enforce", "pace_multiplier": 1.0, "min_daily_allowance_usd": 0.0, "max_daily_allowance_usd": None},
    )
    assert checks[0]["daily_allowance_usd"] == 1.0
    assert abs(checks[0]["available_today_usd"] - 0.25) < 1e-9
    assert checks[0]["allowed"] is False
