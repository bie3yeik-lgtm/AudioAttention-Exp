# Shadow Router Promotion

## Goal

Historical routing must prove itself before controlling paid GPU launches.

Production path initially remains:

```text
Current Cost Router -> launch
```

At the same time:

```text
Historical Router -> shadow recommendation only
```

After the real job finishes, compare actual cost with the shadow prediction.

## Routing regret

For each completed current-router run:

```text
predicted_regret_usd
=
actual current-router cost
-
historical-router predicted cost
```

Positive values mean the Historical Router predicted a cheaper route.

Each run writes:

```text
runs/<job-id>/routing-regret.json
```

## Promotion report

Aggregate files are written to:

```text
router-evaluation/<workload>/promotion-report.json
```

Initial promotion requirements:

```text
>= 20 evaluable runs
>= 70% historical coverage
mean predicted improvement >= $0.02/run
mean relative improvement >= 3%
median improvement >= 0
p95 same-route prediction error <= 35%
```

These thresholds live in:

```text
configs/router-promotion.yaml
```

## Important limitation

Counterfactual regret is not directly observable when Current and Historical
choose different GPUs, because only one route actually executes.

Therefore the first promotion system uses:

- actual cost for the route that really ran;
- predicted cost for the Historical alternative;
- direct prediction-error calibration only on runs where both routers choose
  the same hardware.

This is intentionally conservative.

## Next maturity level

Once shadow evidence is sufficient, introduce a small exploration budget:

```text
5-10% of safe jobs
```

to execute the alternative route and collect real counterfactual performance.

That enables measured regret rather than predicted regret and is the appropriate
next step before full automatic promotion.
