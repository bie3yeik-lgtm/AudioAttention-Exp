# audio-editorial-context

Parakeet TDT-CTC Japanese ASRを固定し、Step-Audio-2-miniをTeacherとして
音声コンテクスト・話者・音響特徴・編集重要度を学習し、最終的に
Premiere Proへ適用可能なKEEP / OPTIONAL / CUTタイムラインを生成する研究・実装プロジェクトです。

## Architecture

Raw Audio
  ├─ Parakeet TDT-CTC -> transcript / timestamps / confidence
  ├─ Acoustic features -> loudness / pitch / pauses / speech rate
  ├─ Speaker pipeline -> diarization / speaker id
  └─ Step-Audio-2-mini Teacher -> context pseudo labels
         ↓
Unified Dataset
         ↓
Student Context Model
         ↓
Editorial Importance Model
         ↓
Timeline Decision Model
         ↓
Premiere-compatible JSON

## Runtime split

- Runpod:
  - Step-Audio teacher experiments
  - Student model training
  - Editorial model training
  - NeMo Gym / RL in later phases
- Hugging Face Jobs:
  - Parakeet fixed inference
  - Feature extraction
  - Dataset validation
  - Golden evaluation
  - Regression tests
- Hugging Face Bucket:
  - Raw audio
  - Derived artifacts
  - Labels
  - Checkpoints
  - Evaluation results

## Repository layout

```text
docker/
  parakeet/Dockerfile
  stepaudio/Dockerfile
  train/Dockerfile
  eval/Dockerfile

configs/
  teacher.yaml
  features.yaml
  context_model.yaml
  editorial_model.yaml
  evaluation.yaml

src/audio_editorial/
  schemas.py
  asr/parakeet.py
  teacher/stepaudio.py
  teacher/prompts.py
  features/acoustics.py
  features/merge.py
  models/context.py
  models/importance.py
  models/timeline.py
  evaluation/metrics.py

scripts/
  transcribe.py
  extract_features.py
  run_teacher.py
  build_dataset.py
  train_context.py
  train_editorial.py
  evaluate_teacher.py
  evaluate_editorial.py
  export_timeline.py
```

## Environment variables

```bash
export HF_TOKEN="hf_..."
export HF_BUCKET="YOUR_ORG/audio-editorial-data"
export HF_DATASET="YOUR_ORG/audio-editorial-dataset"

export PARAKEET_MODEL="nvidia/parakeet-tdt_ctc-0.6b-ja"
export STEPAUDIO_MODEL="stepfun-ai/Step-Audio-2-mini"
```

## HF Bucket layout

```text
audio-editorial-data/
├─ raw/audio/
├─ derived/
│  ├─ parakeet/v1/
│  ├─ acoustics/v1/
│  ├─ teacher/stepaudio-v1/
│  ├─ merged/v1/
│  └─ predictions/
├─ labels/
│  ├─ teacher/
│  └─ human/
├─ checkpoints/
│  ├─ context/
│  └─ editorial/
└─ results/
   ├─ teacher/
   └─ editorial/
```

## Quick start

### 1. Build containers

```bash
docker build -t ghcr.io/YOUR_ORG/audio-editorial-parakeet:0.1.0 \
  -f docker/parakeet/Dockerfile .

docker build -t ghcr.io/YOUR_ORG/audio-editorial-stepaudio:0.1.0 \
  -f docker/stepaudio/Dockerfile .

docker build -t ghcr.io/YOUR_ORG/audio-editorial-train:0.1.0 \
  -f docker/train/Dockerfile .

docker build -t ghcr.io/YOUR_ORG/audio-editorial-eval:0.1.0 \
  -f docker/eval/Dockerfile .
```

### 2. Parakeet transcription

```bash
python scripts/transcribe.py \
  --audio /mnt/hf/raw/audio/sample.wav \
  --output /mnt/hf/derived/parakeet/v1/sample.parquet
```

### 3. Acoustic features

```bash
python scripts/extract_features.py \
  --audio /mnt/hf/raw/audio/sample.wav \
  --segments /mnt/hf/derived/parakeet/v1/sample.parquet \
  --output /mnt/hf/derived/acoustics/v1/sample.parquet
```

### 4. Step-Audio Teacher

```bash
python scripts/run_teacher.py \
  --audio /mnt/hf/raw/audio/sample.wav \
  --segments /mnt/hf/derived/parakeet/v1/sample.parquet \
  --output /mnt/hf/derived/teacher/stepaudio-v1/sample.parquet
```

### 5. Merge dataset

```bash
python scripts/build_dataset.py \
  --asr /mnt/hf/derived/parakeet/v1/sample.parquet \
  --features /mnt/hf/derived/acoustics/v1/sample.parquet \
  --teacher /mnt/hf/derived/teacher/stepaudio-v1/sample.parquet \
  --output /mnt/hf/derived/merged/v1/sample.parquet
```

### 6. Train context model

```bash
python scripts/train_context.py \
  --train /mnt/hf/datasets/train.parquet \
  --valid /mnt/hf/datasets/validation.parquet \
  --output-dir /workspace/checkpoints/context
```

### 7. Train editorial model

```bash
python scripts/train_editorial.py \
  --train /mnt/hf/datasets/train.parquet \
  --valid /mnt/hf/datasets/validation.parquet \
  --context-checkpoint /workspace/checkpoints/context/best.pt \
  --output-dir /workspace/checkpoints/editorial
```

### 8. Evaluate

```bash
python scripts/evaluate_editorial.py \
  --predictions /mnt/hf/results/candidate.parquet \
  --references /mnt/hf/datasets/golden.parquet \
  --output /mnt/hf/results/evaluation.json
```

### 9. Export timeline

```bash
python scripts/export_timeline.py \
  --predictions /mnt/hf/results/candidate.parquet \
  --output timeline.json
```

## Phase roadmap

### Phase 0
Repository / Docker / HF storage固定。

### Phase 1
Parakeet固定ASRの再現性とtimestampを確立。

### Phase 2
Step-Audio Teacher baselineと構造化JSON出力。

### Phase 3
音響特徴を統合し、Teacher reasoningと物理特徴を分離。

### Phase 4
Step-Audioによる大量pseudo-label生成。

### Phase 5
Human labelとのTeacher agreement評価。

### Phase 6
Student Context Modelへ蒸留。

### Phase 7
KEEP / OPTIONAL / CUT Editorial Model学習。

### Phase 8
Timeline Decision Modelで細切れ編集を抑止。

### Phase 9
HF JobsによるGolden / Ablation / Regression評価。

### Phase 10
NeMo Gym / NeMo RLによる編集policy最適化。

### Phase 11
Premiere向けJSON APIへ製品化。

## Additional operational files

- `scripts/predict_editorial.py`
- `scripts/validate_dataset.py`
- `scripts/check_environment.py`
- `deploy/runpod/create-template.sh`
- `deploy/hf-jobs/README.md`
- `.github/workflows/ci.yml`


# Multi-cloud GitHub control plane

This repository additionally manages Runpod and Vast as interchangeable GPU
providers.

See:

- `docs/architecture.md`
- `docs/github-setup.md`
- `infra/README.md`
- `.github/workflows/images.yml`
- `.github/workflows/gpu-job.yml`
- `.github/workflows/provider-cleanup.yml`
- `.github/workflows/hf-eval.yml`
- `.github/workflows/provider-ablation.yml`

Core policy:

```text
GitHub / GHCR = code + immutable runtime
HF Bucket     = persistent source of truth
Runpod/Vast   = disposable GPU compute
HF Jobs       = deterministic validation
```
