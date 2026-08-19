# Hugging Face Jobs

Use HF Jobs for deterministic preprocessing/evaluation, not primary training.

Examples assume the bucket is mounted at `/mnt/hf`.

## Dataset validation

```bash
hf jobs run \
  --flavor cpu-upgrade \
  -v hf://buckets/YOUR_ORG/audio-editorial-data:/mnt/hf \
  ghcr.io/YOUR_ORG/audio-editorial-eval:0.1.0 \
  python /app/scripts/validate_dataset.py \
    --input /mnt/hf/derived/merged/v1/validation.parquet \
    --output /mnt/hf/results/dataset-validation.json
```

## Editorial golden evaluation

```bash
hf jobs run \
  --flavor cpu-upgrade \
  -v hf://buckets/YOUR_ORG/audio-editorial-data:/mnt/hf \
  ghcr.io/YOUR_ORG/audio-editorial-eval:0.1.0 \
  python /app/scripts/evaluate_editorial.py \
    --predictions /mnt/hf/results/candidate.parquet \
    --references /mnt/hf/datasets/golden.parquet \
    --output /mnt/hf/results/editorial-evaluation.json
```
