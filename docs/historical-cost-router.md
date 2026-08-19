# Historical Cost Router

## Purpose

The first Cost Router minimizes current hourly price:

```text
$/GPU-hour
```

The Historical Cost Router minimizes predicted end-to-end job cost:

```text
predicted runtime hours
x
current hourly price
```

with an uncertainty penalty.

## Example

```text
Vast A6000
  current price: $0.30/h
  historical runtime: 10h
  predicted total: $3.00

Runpod L40S
  current price: $0.60/h
  historical runtime: 4h
  predicted total: $2.40
```

The Historical Cost Router selects Runpod L40S.

## Historical data

It consumes:

```text
hf://buckets/<bucket>/runs/*/cost.json
```

using `HfFileSystem.glob()` and `open()`.

Records older than `recency_days` are ignored.

## Robust estimator

For each:

```text
provider + gpu_id + workload
```

the router calculates median normalized runtime.

Teacher:

```text
runtime hours / input audio hours
```

Student:

```text
runtime hours / epochs
```

Median is preferred over mean because failed hosts, cold starts and interrupted
instances can produce large outliers.

## Sparse history

When only a few samples exist, the per-GPU median is shrunk toward a workload
prior.

```text
estimate =
(candidate median * evidence weight + global prior * prior weight)
/
(total weight)
```

With zero history, the router applies a conservative cold-start multiplier.

## Risk adjustment

Historical variability is represented by MAD (median absolute deviation).

Predicted total cost receives a bounded uncertainty penalty, so a provider with
a tiny but highly unstable sample set does not automatically beat a well-known
candidate by a few cents.

## Required cost record fields

Historical selection works best when `cost.json` contains:

```text
provider
gpu_id or flavor
workload
runtime_seconds
estimated_cost_usd

Teacher:
input_audio_hours

Student:
epochs
```

## Migration strategy

### Stage 1

Use current-price Cost Router until each candidate has 3+ successful runs.

### Stage 2

Enable Historical Router in advisory mode and compare its recommendation to the
current router.

### Stage 3

Promote Historical Router to automatic selection.

### Stage 4

Once enough data exists, replace the robust statistical estimator with a
regression model using:

```text
GPU model
provider
audio duration
sample count
batch size
model revision
prompt revision
dataset size
sequence length
cache hit rate
```

Do not jump directly to ML routing with a small dataset.
