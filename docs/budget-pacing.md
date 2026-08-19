# Budget Pacing

Budget Pacing prevents a monthly GPU budget from being consumed too early in the month.
It is enforced at reservation time, in addition to the existing daily/weekly/monthly caps.

## Formula

For each applicable scope (`global` and `workload:<name>`):

```text
committed_before_today = monthly_committed - today_committed
month_available_at_day_start = monthly_limit - committed_before_today
base_daily_allowance = month_available_at_day_start / remaining_calendar_days_including_today

daily_allowance = clamp(
  base_daily_allowance * pace_multiplier,
  min_daily_allowance,
  max_daily_allowance,
)

available_today = daily_allowance - today_committed
```

A reservation is admitted only when its reserved upper-cost amount fits both the normal caps and every enforced pacing check.

This calculation automatically carries unused budget forward. If prior days used less than their implicit share, a later day's allowance rises. If prior days used more, later allowances fall.

## Configuration

```yaml
pacing:
  enabled: true
  mode: enforce        # enforce | advisory
  pace_multiplier: 1.0
  min_daily_allowance_usd: 0.0
  max_daily_allowance_usd: null
```

Environment overrides:

```text
GPU_BUDGET_PACING_ENABLED
GPU_BUDGET_PACING_MODE
GPU_BUDGET_PACING_MULTIPLIER
GPU_BUDGET_PACING_MIN_DAILY_USD
GPU_BUDGET_PACING_MAX_DAILY_USD
```

`advisory` calculates and reports pacing but does not reject reservations.

## Example

Monthly cap: $120
Date: day 21 of a 30-day month
Committed before today: $80
Today committed: $1
Remaining days including today: 10

```text
month_available_at_day_start = 120 - 80 = 40
base_daily_allowance = 40 / 10 = 4
available_today = 4 - 1 = 3
```

A new $2.50 reservation is admitted; a $3.50 reservation is denied in `enforce` mode.

## Interaction with existing limits

Pacing does not replace the monthly cap. A reservation must satisfy:

```text
global daily/weekly/monthly caps
AND workload daily/weekly/monthly caps
AND global monthly pacing
AND workload monthly pacing (when configured)
```

If a scope has no monthly limit, no pacing rule is generated for that scope.
