# AudioAttention-Exp Budget Ledger Patch

Inspected base: `main@8c20441198dd6890da4d1d28393083b3ec11d260`.

Included:

- reservation-based shared Budget Ledger using append-only HF Bucket events;
- global and Teacher/Student daily/weekly/monthly caps via GitHub variables;
- serialized check-and-reserve using GitHub Actions concurrency;
- settlement from `runs/<job-id>/cost.json`;
- release on launch failure / missing cost record;
- TTL garbage collection for stale reservations;
- daily ledger report;
- `Budgeted Unified GPU Job` workflow;
- unit tests for committed/spent/released budget semantics;
- workflow requirements-path regression test;
- fix for malformed Bandit `pip install -r` path;
- `.DS_Store` ignore and cleanup helper;
- cleanup helper for duplicated `infra/infra/` found on current main.

## Apply

From the repository root:

```bash
/path/to/apply-current-main.sh
pytest -q tests/test_budget_ledger.py tests/test_workflow_paths.py
```

The cleanup helper uses `git rm` for `infra/infra` and tracked `.DS_Store` when present.

## Budget variables

All caps default to disabled (`null`). Configure only the limits you want:

```text
GPU_BUDGET_GLOBAL_DAILY_USD
GPU_BUDGET_GLOBAL_WEEKLY_USD
GPU_BUDGET_GLOBAL_MONTHLY_USD
GPU_BUDGET_TEACHER_DAILY_USD
GPU_BUDGET_TEACHER_WEEKLY_USD
GPU_BUDGET_TEACHER_MONTHLY_USD
GPU_BUDGET_STUDENT_DAILY_USD
GPU_BUDGET_STUDENT_WEEKLY_USD
GPU_BUDGET_STUDENT_MONTHLY_USD
```

## Concurrency contract

HF Bucket is the append-only audit store, not a transactional database. The included workflows serialize **mutating ledger operations only** using `budget-ledger-${HF_BUCKET}`. Do not write reservations from another system unless it follows the same single-writer contract or a transactional backend is introduced.
