# Cost Confidence Router

## Purpose

Contextual Regression predicts:

```text
point estimate:
predicted runtime
predicted total cost
```

The Residual Calibration layer predicts:

```text
How wrong is the Contextual model likely to be for this specific job?
```

The Bandit then uses:

```text
predicted cost
± calibrated uncertainty
```

instead of uncertainty derived only from history counts and MAD.

## Training labels

Residual calibration uses completed Contextual evaluations where the Contextual
prediction referred to the route that actually ran.

Targets:

```text
contextual cost APE
contextual runtime APE
```

This avoids fabricating residual labels for unexecuted counterfactual routes.

## Context

Residual prediction includes:

```text
workload
provider
gpu
current quoted price

predicted cost
predicted runtime

audio duration
epochs
samples
batch size
sequence length

model revision
prompt revision
dataset revision
cache state
precision
GPU architecture
framework/container revision
```

## Confidence radius

Initial rule:

```text
uncertainty_fraction
=
predicted_cost_APE
* 1.5
```

clamped to:

```text
3% <= uncertainty <= 50%
```

The multiplier deliberately makes the confidence radius conservative.

## Registry

```text
router-models/residual-calibration/v1/
├─ latest.json
└─ <timestamp>/
   ├─ cost_ape.cbm
   ├─ runtime_ape.cbm
   └─ metadata.json
```

## Fail-closed behavior

If no residual model exists, loading fails, or training data is insufficient:

```text
uncertainty = 25%
```

No paid route depends on a missing model.

## Bandit integration

The next scoring layer should use:

```text
LCB =
predicted cost
-
beta * calibrated_uncertainty_usd
```

for exploration.

Historical evidence-count uncertainty remains available as a fallback and can
be combined conservatively with calibrated uncertainty.

## Recommended deployment

```text
1. residual model training only
2. compare calibrated intervals with realized errors
3. shadow Bandit with calibrated uncertainty
4. active only after interval coverage is acceptable
```
