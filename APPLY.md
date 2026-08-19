# Forecast-aware Budget Pacing

Combined patch baseline:
`main@396a2f2f6732d2f5d04a39aceb5e2c4ed0aec273`.

Use the combined patch if the previous JOB_KIND + Budget Pacing patch has NOT
already been applied:

```bash
git apply --check AudioAttention-Exp-forecast-aware-budget-pacing.patch
git apply AudioAttention-Exp-forecast-aware-budget-pacing.patch
```

If the previous `AudioAttention-Exp-job-kind-budget-pacing.patch` is already
applied, use the incremental patch instead:

```bash
git apply --check AudioAttention-Exp-forecast-aware-budget-pacing-incremental.patch
git apply AudioAttention-Exp-forecast-aware-budget-pacing-incremental.patch
```

Validate:

```bash
python -m pytest -q tests/test_budget_ledger.py tests/test_workflow_paths.py
```

Implemented signals:

- weekday GPU demand from the append-only Budget Ledger;
- scheduled Teacher/Student workload from `configs/budget-demand-forecast.yaml`;
- remaining monthly budget;
- demand-weighted allocation across remaining days;
- global and workload-specific pacing;
- fallback to equal remaining-days pacing when forecast is disabled.

Local validation: False
