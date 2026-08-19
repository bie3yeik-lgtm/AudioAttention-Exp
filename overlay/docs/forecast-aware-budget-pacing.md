# Forecast-aware Budget Pacing

Forecast-aware pacing replaces equal remaining-day allocation with demand-weighted allocation.

## Demand signals

Each remaining day receives a demand weight from three signals:

```text
baseline
weekday historical GPU demand
scheduled Teacher/Student workload
```

The default blend is:

```text
10% baseline
45% weekday history
45% scheduled workload
```

## Historical weekday demand

The ledger reconstructs daily committed GPU cost over the previous 56 days.
For each weekday it calculates a smoothed mean and converts it into a factor
relative to the overall historical daily mean.

For example:

```text
Monday historical factor = 1.35
Friday historical factor = 0.72
```

Sparse weekday history is shrunk toward the neutral factor `1.0`.

## Scheduled workload

`configs/budget-demand-forecast.yaml` can describe expected Teacher/Student work:

```yaml
dates:
  "2026-08-24":
    teacher:
      jobs: 2
      units: 3.0
    student:
      jobs: 1
      units: 2

  "2026-08-25":
    teacher:
      expected_cost_usd: 1.40
```

When `expected_cost_usd` is present it is used directly.
Otherwise `units` is converted with the configured workload fallback cost/unit.

## Allocation

For every remaining calendar day:

```text
demand_weight =
  baseline_weight * 1
  + weekday_weight * weekday_history_factor
  + schedule_weight * scheduled_demand_factor
```

Weights are clamped and the remaining monthly budget is allocated proportionally:

```text
today_allowance =
  month_available_at_day_start
  * today_demand_weight
  / sum(remaining_day_demand_weights)
```

Today's already committed amount is subtracted before admitting a new reservation.

## Scope

Forecast-aware pacing is calculated independently for:

```text
global
workload:teacher
workload:student
```

A reservation must pass every applicable enforced check.

## Operational behavior

- Weekdays that historically consume more GPU receive a larger share.
- Known future Teacher/Student jobs reserve budget for those dates.
- If a scheduled job is removed, future weights rebalance automatically.
- Unused budget still carries forward.
- Monthly hard caps remain authoritative.
- Setting `forecast.enabled=false` falls back to ordinary remaining-days pacing.

## Environment overrides

```text
GPU_BUDGET_FORECAST_ENABLED
GPU_BUDGET_FORECAST_FILE
GPU_BUDGET_FORECAST_LOOKBACK_DAYS
GPU_BUDGET_FORECAST_BASELINE_WEIGHT
GPU_BUDGET_FORECAST_WEEKDAY_WEIGHT
GPU_BUDGET_FORECAST_SCHEDULE_WEIGHT
```

## Limits

The forecast is a pacing heuristic, not a billing prediction.
Hard per-job budget constraints and monthly ledger caps remain the safety boundaries.
