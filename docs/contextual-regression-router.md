# Contextual Regression Router

## Goal

Historical median routing answers:

```text
How fast has this provider/GPU usually been for this workload?
```

Contextual routing answers:

```text
How fast is this provider/GPU likely to be for this specific job?
```

## Job context

Job Spec now supports:

```text
audio_duration_hours
sample_count
dataset_size_bytes
batch_size
sequence_length

model_revision
prompt_revision
dataset_revision

cache_state
precision
gpu_architecture

framework_revision
container_revision
feature_schema_revision

teacher_prompt_tokens_estimate
```

The same context is copied into each `cost.json`.

This makes HF Bucket cost history a self-contained training dataset.

## Model choice

The first production candidate is CatBoost regression.

Reasons:

- small/medium tabular datasets;
- mixed numerical/categorical features;
- native categorical-feature support;
- no manual one-hot encoding required;
- simple CPU training;
- model serialization with `save_model()` / `load_model()`.

Two regressors are trained:

```text
runtime.cbm
  target = runtime_seconds

cost.cbm
  target = estimated_cost_usd
```

## Dynamic cost

Direct historical cost regression can become stale when GPU prices move.

Therefore inference also computes:

```text
predicted runtime
x
current candidate $/h
```

Initial contextual score is:

```text
0.5 * direct CatBoost predicted cost
+
0.5 * runtime-derived current-price cost
```

The blend is intentionally simple and should later be calibrated from shadow
evaluation.

## Registry

Models are stored in HF Bucket:

```text
router-models/contextual/v1/
├─ latest.json
└─ <timestamp>/
   ├─ runtime.cbm
   ├─ cost.cbm
   └─ metadata.json
```

## Training gate

Default:

```text
minimum records = 30
history window = 120 days
validation = newest 20%
```

The newest records are validation data so model quality is measured against more
recent infrastructure behavior.

## Training cadence

The included GitHub Action trains weekly and can also be dispatched manually.

Do not make this model control paid routing immediately.

Recommended maturity:

```text
1. train only
2. contextual advisory
3. contextual shadow
4. compare against Historical Router
5. promote only after measured improvement
```

## Next stage

Add a contextual-model promotion report using:

- validation MAE/MAPE;
- realized routing regret;
- same-route calibration;
- paired probe results.

Then integrate Contextual prediction into the Safe Bandit uncertainty model.
