# Conformal Cost Router

## Purpose

The previous Residual Calibration model estimated:

```text
expected prediction error
```

This layer constructs explicit prediction intervals:

```text
cost_lower <= actual_cost <= cost_upper
```

with a target marginal coverage, initially:

```text
90%
```

## Method

Use split conformal calibration on completed Contextual predictions.

Calibration residual:

```text
|actual cost - predicted cost|
```

The conformal radius is the finite-sample corrected empirical quantile of these
absolute residuals.

For nominal 90% coverage:

```text
q = conformal_quantile(abs residuals, 0.90)

interval = prediction +/- q
```

## Why a separate calibration set

The calibration residuals must come from predictions that were not used merely
as in-sample training fits.

Operationally this repository uses completed shadow/evaluation runs as
calibration evidence.

Only same-route Contextual predictions are eligible.

## Group calibration

When at least 10 observations exist, separate calibration can be used for:

```text
workload + provider + gpu
```

Otherwise the router falls back to a global conformal radius.

This avoids pretending that a tiny GPU/provider subgroup has reliable
calibration.

## Bandit meaning

For cost minimization:

```text
lower confidence cost
=
predicted cost - conformal radius
```

is the optimistic exploration score.

The upper bound is useful for risk controls:

```text
cost_upper
```

can be compared against a hard per-job budget before launching.

## Promotion

Do not use the conformal interval as a production confidence guarantee until
empirical coverage has been measured.

Initial gate:

```text
>= 30 evaluations
85% <= empirical coverage <= 98%
mean relative interval width <= 60%
```

The upper coverage bound is included because intervals that are trivially huge
are not useful.

## Statistical scope

Split conformal gives marginal coverage under exchangeability assumptions.

Cloud GPU workloads can drift over time because of:

```text
software revisions
provider host changes
cache behavior
market changes
dataset shifts
```

Therefore:

- use recent calibration records;
- rebuild calibration regularly;
- measure empirical coverage continuously;
- do not interpret the 90% target as a universal conditional guarantee.

## Next step

Once conformal promotion passes, add a hard budget-aware routing rule:

```text
reject candidate if conformal cost_upper > job budget
```

and optionally optimize:

```text
expected cost
subject to
P(cost <= budget) >= target confidence
```
