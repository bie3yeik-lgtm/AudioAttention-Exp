# Teacher / Student Cost Router

## Goal

Select the cheapest currently usable GPU provider independently for the two
workloads.

```text
Teacher
  Step-Audio-2-mini
  >=48 GB VRAM
  tighter reliability requirements

Student
  Context / Editorial training
  >=24 GB VRAM
  cheap marketplace/consumer GPU acceptable
```

## Repository variables

Recommended initial values:

```text
# Vast: Teacher
VAST_TEACHER_GPU_QUERY=gpu_ram>=48000 num_gpus=1 reliability>0.98 verified=true rentable=true
VAST_TEACHER_DISK_GB=150
VAST_TEACHER_MAX_DPH=0.40

# Vast: Student
VAST_STUDENT_GPU_QUERY=gpu_ram>=24000 num_gpus=1 reliability>0.98 verified=true rentable=true
VAST_STUDENT_DISK_GB=100
VAST_STUDENT_MAX_DPH=0.22

# Runpod: Teacher
RUNPOD_TEACHER_GPU_IDS=NVIDIA RTX A6000,NVIDIA A40,NVIDIA L40S,NVIDIA RTX 6000 Ada Generation
RUNPOD_TEACHER_MAX_DPH=0.55

# Runpod: Student
RUNPOD_STUDENT_GPU_IDS=NVIDIA RTX A5000,NVIDIA GeForce RTX 3090,NVIDIA GeForce RTX 4090
RUNPOD_STUDENT_MAX_DPH=0.35

# Shared
RUNPOD_CLOUD_TYPE=SECURE
COST_ROUTER_PRICE_TOLERANCE=0.01
```

The committed `configs/cost-router.yaml` values are defaults. GitHub repository
variables override them.

## Secrets

```text
VAST_API_KEY
RUNPOD_API_KEY
HF_TOKEN
```

## Selection algorithm

```text
                 workload profile
                  /            \
             teacher          student
                |                |
                v                v
          Vast 48GB+        Vast 24GB+
          own ceiling       own ceiling
                |                |
                +-------+--------+
                        |
                        v
                 Vast best offer
                        |
              +---------+---------+
              |                   |
              v                   v
       Runpod candidate 1   Runpod candidate N
              |                   |
              +---------+---------+
                        |
                        v
              cheapest valid Runpod
                        |
                        v
                 compare USD/hour
                        |
             +----------+----------+
             |                     |
            Vast                 Runpod
```

A provider is valid only if it is available and does not exceed its own price
ceiling.

If the difference between the two cheapest providers is within
`COST_ROUTER_PRICE_TOLERANCE`, Runpod is preferred by default because it is the
stable fallback service. This can be changed in `select_provider.py`.

## Why Runpod volume is zero

HF Storage Bucket is the persistent source of truth. The cost router therefore
uses Runpod local/container storage as disposable cache and defaults persistent
Runpod volume to zero. This also makes the hourly GPU comparison more meaningful.

## Workflows

- `teacher-job.yml`
  - calls `reusable-cost-router.yml` with `profile=teacher`
  - starts Step-Audio Teacher on the selected provider.

- `student-job.yml`
  - calls the router with `profile=student`
  - starts Context or Editorial training.

- `reusable-cost-router.yml`
  - queries Vast and Runpod
  - returns provider/GPU/price as workflow outputs.

## Failure policy

Routing failure:

```text
No Vast offer <= Vast ceiling
AND
No Runpod GPU <= Runpod ceiling
    ->
fail closed
```

Do not silently start an over-ceiling GPU.

Instance-creation race should be handled as a second layer:
if the selected Vast offer disappears before creation, rerun the router or
fall back to the already-inspected Runpod candidate.
