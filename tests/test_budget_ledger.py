from datetime import datetime, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "infra" / "budget_ledger"))

from core import check_limits, period_keys, reservation_state, usage_for_period


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
