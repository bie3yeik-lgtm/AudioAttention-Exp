# AudioAttention-Exp JOB_KIND + Budget Pacing patch

Baseline: `main@396a2f2f6732d2f5d04a39aceb5e2c4ed0aec273`.

## Apply

```bash
git checkout main
git pull --ff-only
git apply --check AudioAttention-Exp-job-kind-budget-pacing.patch
git apply AudioAttention-Exp-job-kind-budget-pacing.patch
python -m pytest -q tests/test_budget_ledger.py tests/test_workflow_paths.py
```

## Changes

- Fixes `JOB_KIND`: resolves `.runtime_env.JOB_KIND // .workload` in one shell variable before writing `$GITHUB_ENV`.
- Adds remaining-days monthly Budget Pacing.
- Applies pacing independently to global and workload monthly limits.
- Unused monthly budget automatically carries forward.
- Supports `enforce` and `advisory` modes.
- Adds GitHub environment overrides for pacing.
- Adds pacing state to Budget Ledger reports.
- Adds regression tests and `docs/budget-pacing.md`.

Validated locally: `10 passed`.
