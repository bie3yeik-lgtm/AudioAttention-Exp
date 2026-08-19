# Forecast Stabilization

This hardens automatic demand forecasting used by Budget Pacing.

- queued/running `budgeted|<job_spec>|<units>` runs are collected before future Job Specs;
- the same `job_id` is counted once as it transitions planned -> queued -> reserved;
- already reserved jobs are excluded because the Budget Ledger already counts them as committed;
- repeated `source_id` merges are idempotent;
- GitHub Actions query failures are reported as `health: degraded` and `confidence: medium|low`;
- `actions.failure_mode: fail_closed` or `GPU_BUDGET_FORECAST_ACTIONS_FAILURE_MODE=fail_closed` aborts forecast generation on API failure;
- generated YAML includes source counts, exclusions and API errors;
- legacy root apply/package helpers are removed by the bundle cleanup step.

`confidence` describes source completeness only; it is not a statistical confidence interval.
