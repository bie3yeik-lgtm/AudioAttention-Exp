# Cloud infrastructure

## Contract

Both Runpod and Vast execute the same immutable GHCR image and write durable
artifacts to the same Hugging Face Storage Bucket.

Common paths:

```text
HF_ROOT=/mnt/hf
/workspace/cache            provider-local cache
/mnt/hf/runs/<RUN_ID>/      durable per-run result
```

Do not use HF Storage Buckets as a distributed lock. Use unique `RUN_ID`s.

## Runpod

CI uses the official REST API under `https://rest.runpod.io/v1`.
For local interactive administration you can also use `runpodctl`.

```bash
bash <(curl -sL cli.runpod.io)
runpodctl config --apiKey "$RUNPOD_API_KEY"
runpodctl gpu list
runpodctl pod list --all
```

## Vast

```bash
pip install --upgrade vastai
vastai set api-key "$VAST_API_KEY"

vastai search offers \
  'gpu_ram>=48000 num_gpus=1 reliability>0.98 verified=true rentable=true' \
  --order=dph_total

vastai show instances
```

## Hugging Face

HF Jobs is used for deterministic validation and golden evaluation.

```bash
pip install --upgrade 'huggingface_hub>=1.8.0'
hf jobs run \
  -v hf://buckets/YOUR_ORG/audio-editorial-data:/mnt/hf \
  IMAGE COMMAND...
```
