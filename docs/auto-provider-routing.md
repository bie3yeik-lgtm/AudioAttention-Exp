# Automatic Vast -> Runpod routing

`auto-provider-gpu-job.yml` uses Vast first when the configured offer is
currently valid and available.

## Required GitHub variables

```text
HF_BUCKET=YOUR_ORG/audio-editorial-data

VAST_GPU_QUERY=gpu_ram>=48000 num_gpus=1 reliability>0.98 verified=true rentable=true
VAST_DISK_GB=150

RUNPOD_CLOUD_TYPE=SECURE
RUNPOD_REGISTRY_AUTH_ID=<optional>
```

## Required GitHub secrets

```text
HF_TOKEN
VAST_API_KEY
RUNPOD_API_KEY
```

## Routing

```text
validate VAST_DISK_GB
        |
        v
vastai search offers
VAST_GPU_QUERY + disk_space>=VAST_DISK_GB
        |
        +-- invalid/search error --------> Runpod
        |
        +-- zero offers -----------------> Runpod
        |
        v
matching offer
        |
        v
Vast create --cancel-unavail
        |
        +-- create failed ---------------> Runpod
        |
        v
      Vast
```

`--storage VAST_DISK_GB` is retained because Vast uses it in offer pricing,
while `disk_space>=VAST_DISK_GB` is appended to the query to require enough
actual disk capacity.

`--cancel-unavail` avoids creating a stopped Vast instance if the selected
offer disappears between validation and rental.
