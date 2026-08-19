# Cloud architecture

```text
                         GitHub
                           |
               +-----------+-----------+
               |                       |
             Actions                  GHCR
               |               immutable Docker images
               |
      +--------+--------+
      |                 |
   Runpod              Vast
  stable GPU        marketplace GPU
      |                 |
      +--------+--------+
               |
            /mnt/hf
               |
        Hugging Face Bucket
        single source of truth
               |
        +------+------+
        |             |
      data          results
        |             |
        +------HF Jobs+
          deterministic
          evaluation
```

Responsibilities:

- GitHub: source, CI/CD, orchestration.
- GHCR: immutable execution images identified by digest/SHA.
- HF Bucket: raw audio, derived data, labels, checkpoints, run outputs.
- Runpod: stable interactive/teacher/training capacity.
- Vast: low-cost/fallback/batch capacity.
- HF Jobs: deterministic dataset validation and golden evaluation.
