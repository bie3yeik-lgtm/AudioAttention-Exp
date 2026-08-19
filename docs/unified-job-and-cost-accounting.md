# Unified Job + Cost Accounting

## Objective

Move from:

```text
choose provider
-> launch
```

to:

```text
Job Spec
-> Execution Router
-> Provider launcher
-> Completion watcher
-> Cost accounting
-> Cleanup
-> HF Bucket lifecycle record
```

## Job Spec

A job is represented by one JSON file validated against
`schemas/job-spec.schema.json`.

The spec is provider-neutral.

```json
{
  "schema_version": "1.0",
  "job_id": "teacher-001",
  "workload": "teacher",
  "image": "ghcr.io/org/audio-editorial-stepaudio:sha-...",
  "command": "/app/deploy/common/run_cloud_job.sh",
  "hf_bucket": "org/audio-editorial-data",
  "timeout_seconds": 14400,
  "accounting": {
    "input_audio_hours": 1.0
  }
}
```

## Completion contract

Provider workers write one of:

```text
runs/<job_id>/_SUCCESS.json
runs/<job_id>/_FAILED.json
```

HF Jobs may additionally be considered complete when its native Job status reaches
a terminal stage.

## Accounting records

Each run produces:

```text
runs/<job_id>/cost.json
runs/<job_id>/lifecycle.json
```

`cost.json` contains:

```text
quoted price snapshot
provider-reported price snapshot when available
runtime seconds
estimated cost
cost / input audio hour
cost / epoch
cost / 1000 samples
```

This is intentionally named an estimate and is not treated as the provider invoice.

## Runtime measurement

### HF Jobs

Use native `started_at` and `finished_at` from `JobInfo` when available.

### Runpod

Use observed wall-clock launch to terminal marker. Near completion, query the Pod
REST API and snapshot `adjustedCostPerHr` or `costPerHr`.

### Vast

Use observed wall-clock launch to terminal marker. Near completion, query
`vastai show instance --raw` and snapshot available hourly price fields.

## Cleanup

### Runpod

Delete Pod via:

```text
DELETE /v1/pods/<pod-id>
```

### Vast

Destroy instance:

```text
vastai destroy instance <id>
```

### HF Jobs

Completed Jobs require no cleanup. A watchdog timeout triggers Job cancellation.

## Why HF Bucket is the lifecycle bus

The same completion markers work for all providers. Hugging Face Buckets support
read/write access through `HfFileSystem` and `hf://buckets/...` paths.

This keeps GitHub Actions independent of provider-specific log APIs.

## Cost report

```bash
python scripts/summarize_costs.py \
  --bucket YOUR_ORG/audio-editorial-data \
  --output costs.parquet
```

Over time this dataset can answer:

- Which provider is cheapest for Step-Audio Teacher?
- Cost per input audio hour.
- Cost per Student epoch.
- Whether a faster but more expensive GPU lowers total job cost.
- Whether the current price ceilings are too restrictive.


## Workload vs runtime job kind

`workload` is used by the cost/execution router.

`runtime_env.JOB_KIND` is used by the container.

Example Student Context job:

```json
{
  "workload": "student",
  "runtime_env": {
    "JOB_KIND": "context-train",
    "TRAIN_REL": "datasets/train.parquet",
    "VALID_REL": "datasets/validation.parquet",
    "EPOCHS": "10"
  }
}
```

This separation allows Context and Editorial training to share the `student`
cost profile without conflating routing policy with application commands.
