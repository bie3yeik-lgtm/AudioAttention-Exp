# Contextual Model Promotion Gate

## Purpose

A Contextual model must not become the Bandit's primary cost predictor merely
because training succeeded.

Promotion requires realized evidence that it is better than the Historical
Router.

## Per-run evaluation

After a completed run has both:

```text
runs/<job-id>/contextual-decision.json
runs/<job-id>/cost.json
```

the evaluator writes:

```text
runs/<job-id>/contextual-evaluation.json
```

It measures:

```text
Contextual cost APE
Contextual runtime APE

Historical cost error when Historical predicted the executed route
Contextual cost error when Contextual predicted the executed route

Direct Contextual-vs-Historical error delta
when both predicted the same executed route
```

## Why same-route calibration matters

When Historical recommends A6000 and Contextual recommends L40S, but only A6000
actually runs, L40S's true cost is unobservable.

Therefore direct prediction-error superiority is only asserted on runs where the
compared model predicted the route that actually executed.

Paired probes remain the source of direct alternative-route evidence.

## Promotion thresholds

Default:

```text
>= 30 contextual evaluations
>= 10 both-model same-route evaluations
>= 5 paired-probe winner evaluations

evaluation coverage >= 70%

Contextual cost MAPE <= 25%
Contextual runtime MAPE <= 30%

Contextual MAE improves over Historical >= 5%

paired-route winner accuracy >= 60%

median Contextual-Historical absolute-error delta <= 0
```

## Model source gate

The Bandit prediction source is:

```text
Contextual promotion PASS
    -> Contextual predictions

otherwise
    -> Historical predictions
```

This is fail-closed.

## HF Bucket reports

```text
router-evaluation/<workload>/
├─ promotion-report.json
├─ contextual-promotion-report.json
└─ paired/
```

## Next step

After Contextual promotion is trustworthy, connect its per-candidate prediction
residuals to the Bandit uncertainty estimate.

That replaces today's evidence-count/MAD uncertainty with a calibrated
context-dependent uncertainty model.


## Bandit integration

`Safe Bandit Router` now accepts:

```text
prediction_source=auto|historical|contextual
job_spec_path=<job spec>
```

Default `auto` behavior:

```text
contextual promotion PASS + job spec available
    -> Contextual candidate predictions feed the Bandit

otherwise
    -> Historical candidate predictions feed the Bandit
```

Even after Contextual promotion, the Historical greedy route remains the safe
baseline used by the Bandit's cost guards and fail-closed behavior.
