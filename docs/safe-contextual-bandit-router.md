# Safe Contextual Bandit / UCB-style Cost Router

## Purpose

The previous layer used fixed epsilon exploration.

This layer replaces fixed random exploration with uncertainty-aware routing.

The router asks:

```text
Which currently valid candidate has the best optimistic total-cost bound?
```

For cost minimization:

```text
LCB
=
predicted risk-adjusted total cost
-
exploration bonus
```

Lower is better.

## Why LCB instead of ordinary UCB

UCB is usually described for reward maximization.

This project minimizes cost, so the equivalent optimistic score is a lower
confidence bound.

Unknown candidates get an exploration bonus, temporarily lowering their score.

## Evidence

Candidate uncertainty uses:

```text
ordinary historical runs
+
paired probe observations * paired_observation_weight
```

Paired probes receive higher weight because they directly compare the same small
job on two routes.

## Safety guards

Bandit exploration never overrides:

- Vast / Runpod price ceilings;
- current availability filtering;
- maximum job size for exploration;
- maximum predicted extra total cost;
- maximum relative cost premium.

The Historical greedy candidate is always retained as a safe baseline.

## Modes

### advisory

Calculate and store Bandit recommendation only.

Paid selection remains Historical greedy.

### shadow

Same paid behavior as advisory, but intended for routine production shadowing.

This is the repository default.

### active

Bandit recommendation may control paid execution.

Active mode is fail-closed.

By default it requires:

```text
Historical promotion report = PASS
AND
>= 5 paired probes for the workload
```

If either is missing, the effective mode automatically becomes `shadow`.

## Initial configuration

```text
beta = 0.20

Teacher:
  max units = 2 input audio hours

Student:
  max units = 5 epochs

max predicted extra cost = $0.20
max relative premium = 25%
paired observation weight = 3
```

These values are deliberately conservative.

## Candidate uncertainty

With no observations:

```text
uncertainty fraction = 40%
```

As effective evidence increases, uncertainty falls approximately as:

```text
1 / sqrt(n)
```

Historical MAD contributes empirical variability.

A minimum uncertainty floor prevents the router from becoming falsely certain.

## Decision output

Each decision is stored as:

```text
runs/<job-id>/bandit-decision.json
```

It records:

- requested/effective mode;
- Historical greedy route;
- Bandit recommendation;
- paid selected route;
- promotion gate state;
- paired-probe count;
- per-candidate LCB score;
- evidence saturation;
- uncertainty;
- safety guard result.

## Deployment sequence

Recommended:

```text
Stage 1
bandit mode = advisory

Stage 2
bandit mode = shadow

Stage 3
Historical Router promotion PASS
+ paired probes >= threshold

Stage 4
small jobs only: active

Stage 5
increase max units slowly after measured outcomes remain safe
```

Do not immediately enable active Bandit routing for large Teacher batches.

## Next stage

After enough active/shadow decisions, introduce richer context:

```text
audio duration
dataset size
batch size
prompt revision
model revision
cache warm/cold state
GPU architecture
provider reliability
```

and replace the scalar uncertainty model with a real contextual regression +
bandit policy.
