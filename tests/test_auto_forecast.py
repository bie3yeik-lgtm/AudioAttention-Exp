import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infra" / "budget_ledger"))

from auto_forecast import add_demand, decode_budgeted_run, estimate_spec


def fc():
    return {
        "fallback_cost_per_unit_usd": {"teacher": 0.4, "student": 0.25},
        "fallback_cost_per_job_usd": {"teacher": 0.1, "student": 0.1},
    }


def test_decode_budgeted_run():
    assert decode_budgeted_run(
        "budgeted|plans/jobs/a.json|2.5", "budgeted|"
    ) == ("plans/jobs/a.json", 2.5)


def test_estimate_explicit_cost():
    wl, jobs, units, cost = estimate_spec(
        {
            "workload": "teacher",
            "metadata": {"forecast": {"expected_cost_usd": 1.2, "jobs": 2}},
        },
        None,
        fc(),
    )
    assert wl == "teacher"
    assert jobs == 2
    assert cost == 1.2


def test_add_demand_aggregates():
    schedule = {"dates": {}}
    add_demand(schedule, "2026-08-25", "student", 1, 2, 0.5, "a")
    add_demand(schedule, "2026-08-25", "student", 1, 3, 0.7, "b")
    item = schedule["dates"]["2026-08-25"]["student"]
    assert item["jobs"] == 2
    assert item["units"] == 5
    assert abs(item["expected_cost_usd"] - 1.2) < 1e-9
    assert item["sources"] == ["a", "b"]
