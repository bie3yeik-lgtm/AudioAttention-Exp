# GitHub setup

## Repository variables

Repository or Environment variables:

```text
HF_BUCKET=YOUR_ORG/audio-editorial-data

RUNPOD_CLOUD_TYPE=SECURE
RUNPOD_REGISTRY_AUTH_ID=<optional Runpod registry auth ID>

VAST_GPU_QUERY=gpu_ram>=48000 num_gpus=1 reliability>0.98 verified=true rentable=true
VAST_DISK_GB=150
```

## Secrets

```text
HF_TOKEN
RUNPOD_API_KEY
VAST_API_KEY
```

If GHCR packages are private, Runpod also needs a registry auth entry that can pull
`ghcr.io/<org>/audio-editorial-*`.

Vast must likewise be able to pull the image. The simplest configuration for a
research repository is to make the runtime GHCR packages public while keeping
source/data private. If private images are required, add a scoped GHCR pull token
to Vast's image/instance configuration rather than embedding it in source.

## Environments

Create:

```text
gpu-runpod
gpu-vast
hf-evaluation
release
```

Recommended protection:

- `gpu-runpod`: required reviewer
- `gpu-vast`: required reviewer
- `release`: required reviewer
- `hf-evaluation`: no reviewer needed for routine validation

This makes accidental paid GPU launches harder.

## Branches

Recommended:

```text
main       release-quality branch
develop    integration branch
feature/*  normal work
```

PRs target `develop`; release PRs merge `develop -> main`.

## GHCR convention

```text
ghcr.io/<org>/audio-editorial-stepaudio:sha-<40-char-sha>
ghcr.io/<org>/audio-editorial-train:sha-<40-char-sha>
ghcr.io/<org>/audio-editorial-eval:sha-<40-char-sha>
ghcr.io/<org>/audio-editorial-parakeet:sha-<40-char-sha>
```

Use the SHA tag in Runpod/Vast jobs. `main` is only a convenience tag.

## HF artifact convention

```text
runs/<provider>-<github-run-id>-<attempt>/
  environment.json
  ...
  _SUCCESS.json
```

Never let multiple workers overwrite a shared `latest.parquet`.
