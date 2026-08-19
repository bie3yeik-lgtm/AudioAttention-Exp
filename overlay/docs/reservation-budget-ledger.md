# Reservation-based Budget Ledger

The per-job Budget Router limits a single job. The Budget Ledger limits concurrent and accumulated spend across jobs.

Lifecycle:

```text
Budget Router
  -> choose route and cost upper bound
  -> reserve shared budget
  -> launch
  -> write cost.json
  -> settle reservation with actual/estimated realized cost
  -> release unused reservation
```

## Storage model

HF Bucket stores append-only events:

```text
budget-ledger/v1/events/YYYY/MM/*.json
```

Event types are `reservation`, `settlement`, and `release`. There is no mutable central balance file, so the complete audit trail remains reconstructable.

## Concurrency

HF Bucket does not provide the transaction primitive required for atomic check-and-reserve. Therefore all GitHub Actions that mutate the ledger use the same `concurrency.group` (`budget-ledger-<HF_BUCKET>`). The reservation step performs check + append while holding that single-writer gate.

This protects GitHub Actions launched from this repository. External writers must use the same serialization contract or a future transactional backend.

## Limits

Limits can be applied independently to:

- global daily / weekly / monthly spend;
- Teacher daily / weekly / monthly spend;
- Student daily / weekly / monthly spend.

The YAML defaults are `null` (disabled). Set repository variables such as:

```text
GPU_BUDGET_GLOBAL_MONTHLY_USD
GPU_BUDGET_TEACHER_MONTHLY_USD
GPU_BUDGET_STUDENT_MONTHLY_USD
```

No dollar amount is hard-coded as a recommended production budget.

## Reservation amount

`budgeted-unified-job.yml` reserves the selected candidate's Conformal upper cost when available; otherwise it reserves expected cost. Settlement replaces the reservation with `cost.json:estimated_cost_usd` and records the variance.

## TTL / crash recovery

Open reservations expire after 12 hours by default. `budget-ledger-gc.yml` runs hourly and emits release events. A late settlement always takes precedence over a release when the ledger is folded, so a real cost can still be accounted after a premature release.

## Apply to the current repository

This bundle also includes stabilization work identified during repository inspection:

- fix the malformed `infra/residual_calibration:infra/conformal_router/requirements.txt` path in `bandit-router.yml`;
- ignore/remove `.DS_Store`;
- remove the duplicated `infra/infra/` tree;
- add Router/Ledger dependencies to CI;
- add unit tests for ledger accounting and workflow path checks.
