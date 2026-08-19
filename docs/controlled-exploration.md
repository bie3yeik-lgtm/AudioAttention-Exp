# Controlled Exploration and Paired Probes

## Why this layer exists

Shadow routing alone cannot observe the real cost of an unexecuted alternative.

A 5% exploration policy improves coverage, but it still does not reveal the
counterfactual outcome for the exact same job.

Therefore this repository separates:

1. Randomized controlled exploration.
2. Paired probes on tiny benchmark jobs.

## 1. Controlled exploration

Default:

```text
95% exploitation
  -> Historical Router greedy candidate

5% exploration
  -> safe alternative candidate
```

Exploration is only allowed when:

- workload is Teacher or Student;
- job size is below `max_units`;
- the alternative is still inside provider price ceilings;
- predicted extra total cost is below an absolute guard;
- predicted relative premium is below a percentage guard.

Assignment is deterministic from `job_id`, making reruns reproducible.

## Underexplored candidate preference

When exploration is selected, candidates with less historical evidence are
preferred.

This avoids wasting exploration budget on routes already measured many times.

## 2. Paired probes

A paired probe runs the exact same small benchmark input twice:

```text
same input
   |
   +-> primary route
   |
   +-> secondary route
```

Only paired probes produce directly measured route-vs-route cost evidence for
that input.

They are intentionally constrained:

```text
Teacher <= 0.5 input audio hours
Student <= 1 epoch
predicted second-route cost <= $0.35
probability = 2%
```

## Outputs

Exploration decision:

```text
mode
selected provider/GPU
greedy provider/GPU
epsilon
assignment value
```

Paired result:

```text
router-evaluation/<workload>/paired/<probe-id>.json
```

contains actual normalized cost for both routes.

## Next step

Once paired data accumulates, use it to calibrate:

- GPU speed ratios;
- provider-specific overhead;
- prediction uncertainty;
- exploration rate.

Then replace fixed epsilon with a contextual bandit/UCB policy only after
sufficient paired observations exist.
