# Budget-Constrained Router

## Goal

The router now supports explicit per-job budget policy.

Instead of only:

```text
minimize predicted total cost
```

it can enforce:

```text
choose a candidate whose conformal upper cost bound is within budget
```

## Job Spec

```json
{
  "budget": {
    "mode": "hard_budget",
    "max_cost_usd": 1.0,
    "target_confidence": 0.90,
    "soft_penalty_multiplier": 3.0
  }
}
```

## Modes

### unbounded

Ignore job budget and optimize expected/predicted cost.

### hard_budget

Candidate is eligible only when:

```text
conformal upper cost <= max_cost_usd + tolerance
```

If no candidate satisfies the budget, the router fails closed.

No expensive fallback is launched silently.

By default hard-budget routing requires:

```text
Conformal promotion PASS
```

because an unvalidated confidence interval should not be used as a hard spending
guarantee.

### soft_budget

All candidates remain eligible, but budget excess receives a penalty:

```text
score
=
expected cost
+
penalty multiplier * max(0, upper cost - budget)
```

This is useful when the budget is a preference rather than a strict cap.

## Why use the upper bound

For a hard budget, expected cost is insufficient.

Example:

```text
A:
expected = $0.80
90% interval = [$0.60, $1.20]

B:
expected = $0.88
90% interval = [$0.80, $0.96]

budget = $1.00
```

A is cheaper on average but violates the budget risk constraint.

B is selected.

## Fail-closed cases

Hard-budget routing rejects execution when:

- Conformal calibration is missing;
- Conformal promotion has not passed;
- no candidate has an upper bound within budget;
- existing provider price ceilings leave no valid candidate.

## Optimization interpretation

The practical policy approximates:

```text
minimize expected cost
subject to
upper confidence bound <= budget
```

which corresponds operationally to:

```text
P(cost <= budget) >= nominal conformal coverage
```

subject to conformal assumptions and observed empirical calibration.

## Next step

Add portfolio/monthly budget accounting:

```text
daily budget
weekly budget
monthly GPU budget
per-workload budget
```

and reserve funds before launch so multiple concurrent GitHub Actions cannot
independently overspend the same shared budget.
