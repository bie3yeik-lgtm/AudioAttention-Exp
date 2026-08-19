from datetime import datetime, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "infra" / "budget_ledger"))

from core import check_limits, forecast_aware_pacing_checks, pacing_checks, period_keys, reservation_state, usage_for_period
from forecast import scheduled_cost_usd, weekday_factors


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



def test_weekday_factors_prefer_high_demand_weekday():
    from datetime import date

    demand = {
        date(2026, 8, 3): 4.0,   # Monday
        date(2026, 8, 10): 4.0,  # Monday
        date(2026, 8, 4): 1.0,   # Tuesday
        date(2026, 8, 11): 1.0,  # Tuesday
    }
    factors = weekday_factors(demand, smoothing_days=0.0)
    assert factors[0] > factors[1]


def test_forecast_aware_pacing_reserves_more_for_scheduled_day():
    now = datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc)
    limits = {
        "global": {"monthly": 12.0},
        "workload:teacher": {"monthly": None},
    }
    pacing = {
        "enabled": True,
        "mode": "enforce",
        "pace_multiplier": 1.0,
        "min_daily_allowance_usd": 0.0,
        "max_daily_allowance_usd": None,
    }
    forecast_cfg = {
        "enabled": True,
        "history_lookback_days": 56,
        "weights": {
            "baseline": 0.1,
            "weekday_history": 0.0,
            "scheduled_jobs": 0.9,
        },
        "weekday_smoothing_days": 2.0,
        "min_day_weight": 0.25,
        "max_day_weight": 4.0,
        "fallback_cost_per_unit_usd": {"teacher": 1.0, "student": 1.0},
    }

    today = period_keys(now, "Asia/Tokyo")["daily"]
    schedule = {
        "dates": {
            today: {
                "teacher": {
                    "expected_cost_usd": 10.0
                }
            }
        }
    }

    checks = forecast_aware_pacing_checks(
        [],
        workload="teacher",
        amount_usd=1.0,
        now=now,
        tz_name="Asia/Tokyo",
        limits=limits,
        pacing=pacing,
        forecast_cfg=forecast_cfg,
        schedule=schedule,
    )
    assert checks[0]["strategy"] == "forecast_aware"
    assert checks[0]["scheduled_cost_usd"] == 10.0
    assert checks[0]["today_demand_weight"] > 1.0


def test_forecast_disabled_falls_back_to_equal_remaining_days():
    now = datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc)
    checks = forecast_aware_pacing_checks(
        [],
        workload="teacher",
        amount_usd=1.0,
        now=now,
        tz_name="Asia/Tokyo",
        limits={"global": {"monthly": 12.0}, "workload:teacher": {"monthly": None}},
        pacing={
            "enabled": True,
            "mode": "enforce",
            "pace_multiplier": 1.0,
            "min_daily_allowance_usd": 0.0,
            "max_daily_allowance_usd": None,
        },
        forecast_cfg={"enabled": False},
        schedule={"dates": {}},
    )
    assert checks[0]["daily_allowance_usd"] == 1.0



def test_zero_demand_days_are_included_in_weekday_history():
    from forecast import historical_daily_demand
    now = datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc)
    demand = historical_daily_demand([], scope="global", now=now, tz_name="Asia/Tokyo", lookback_days=14)
    assert len(demand) == 14
    assert all(v == 0.0 for v in demand.values())


def test_scheduled_jobs_count_contributes_to_cost():
    from datetime import date
    schedule = {"dates": {"2026-08-25": {"teacher": {"jobs": 3}}}}
    cost = scheduled_cost_usd(schedule, day=date(2026, 8, 25), scope="workload:teacher", fallback_cost_per_unit_usd={"teacher": 0.4}, fallback_cost_per_job_usd={"teacher": 0.5})
    assert cost == 1.5
