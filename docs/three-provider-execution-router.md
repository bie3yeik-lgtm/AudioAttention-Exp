# Three-provider Execution Router

## Scope

This layer sits above the existing Teacher/Student GPU Cost Router.

```text
                       workload
                          |
        +-----------------+------------------+
        |                 |                  |
       CPU             GPU train        Golden GPU
        |                 |                  |
        v                 v                  v
    HF Jobs        Vast <-> Runpod    Vast/Runpod/HF
```

## Why

Current HF Jobs pricing makes CPU jobs extremely inexpensive:

```text
cpu-basic   $0.01/h
cpu-upgrade $0.03/h
```

GPU flavors are much more expensive:

```text
L4 24GB     $0.80/h
L40S 48GB   $1.80/h
A100 80GB   $2.50/h
```

Therefore the router does not treat all providers symmetrically.

## Workload policy

### preprocess / validate / golden-cpu

Always use HF Jobs while its selected CPU flavor remains below the configured
ceiling.

Recommended:

```text
HF_CPU_FLAVOR=cpu-upgrade
HF_CPU_MAX_DPH=0.05
```

### teacher

Use the existing Teacher Cost Router:

```text
Vast 48GB+
vs
Runpod 48GB+
```

HF Jobs GPU is deliberately excluded from routine Teacher generation.

### student

Use:

```text
Vast 24GB+
vs
Runpod 24GB+
```

HF Jobs GPU is deliberately excluded from routine Student training.

### golden-gpu

Compare:

```text
best valid Vast/Runpod candidate
vs
HF_GOLDEN_GPU_FLAVOR
```

Recommended baseline:

```text
HF_GOLDEN_GPU_FLAVOR=l40sx1
HF_GOLDEN_GPU_MAX_DPH=2.00
```

This allows a reproducible fixed hardware benchmark when it is actually worth
the premium.

## Repository variables

```text
HF_NAMESPACE=YOUR_ORG
HF_CPU_FLAVOR=cpu-upgrade
HF_CPU_MAX_DPH=0.05

HF_GOLDEN_GPU_FLAVOR=l40sx1
HF_GOLDEN_GPU_MAX_DPH=2.00
```

Keep the existing Vast and Runpod variables:

```text
VAST_TEACHER_GPU_QUERY
VAST_TEACHER_MAX_DPH
VAST_TEACHER_DISK_GB

VAST_STUDENT_GPU_QUERY
VAST_STUDENT_MAX_DPH
VAST_STUDENT_DISK_GB

RUNPOD_TEACHER_GPU_IDS
RUNPOD_TEACHER_MAX_DPH

RUNPOD_STUDENT_GPU_IDS
RUNPOD_STUDENT_MAX_DPH

RUNPOD_CLOUD_TYPE
COST_ROUTER_PRICE_TOLERANCE
```

## HF Jobs billing behavior

Jobs are billed by hardware usage and only while Starting or Running.
The CLI can launch detached jobs and later inspect/log/wait/cancel them.

This makes GitHub Actions a control plane rather than a long-running compute
host.

## Next extension

The remaining missing piece is a unified one-shot launcher that can accept
an arbitrary job descriptor and launch:

```text
hf_jobs
vast
runpod
```

with one common JSON contract, plus automatic cleanup and budget accounting.
