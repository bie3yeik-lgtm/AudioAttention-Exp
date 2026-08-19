# Automatic Demand Forecast

Forecast-aware Budget Pacing rebuilds its demand schedule immediately before reservation/reporting into `$RUNNER_TEMP`.
It merges the manual `configs/budget-demand-forecast.yaml` with three sources:

1. GitHub Actions runs in queued/requested/waiting/pending/in-progress states.
2. Future `on.schedule` cron occurrences for explicitly mapped GPU workflows.
3. Future-dated Job Specs under the globs in `configs/forecast-sources.yaml`.

`Budgeted Unified GPU Job` uses this run-name:

```text
budgeted|<job_spec_path>|<units>
```

That lets a queued run resolve its Job Spec. The current run and runs whose Job Spec already has a Budget Ledger reservation are excluded to avoid double counting.

Future Job Specs remain schema-compatible by placing scheduling metadata under `metadata.forecast`:

```json
{
  "metadata": {
    "forecast": {
      "scheduled_at": "2026-08-25T10:00:00+09:00",
      "jobs": 1,
      "units": 2.5,
      "expected_cost_usd": 1.2
    }
  }
}
```

GitHub does not materialize future workflow-run objects before cron execution, so future scheduled demand is expanded from workflow YAML with `croniter`. Only workflows explicitly listed in `workflow_rules` are counted.

The generated forecast is temporary and is not committed back to the repository.
