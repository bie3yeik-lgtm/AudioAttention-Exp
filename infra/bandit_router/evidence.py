from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any

from huggingface_hub import HfFileSystem


def identity(provider: str, gpu_id: str | None) -> str:
    return f"{provider}::{gpu_id or 'unknown'}"


def load_paired_evidence(
    bucket: str,
    *,
    workload: str,
) -> dict[str, dict[str, float]]:
    """
    Aggregate measured paired-probe evidence by provider/GPU.

    Returns:
      {
        "vast::RTX A6000": {
          "paired_observations": 4,
          "paired_wins": 3,
          "paired_losses": 1
        }
      }
    """
    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))
    paths = fs.glob(
        f"hf://buckets/{bucket}/router-evaluation/{workload}/paired/*.json"
    )

    out: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "paired_observations": 0.0,
            "paired_wins": 0.0,
            "paired_losses": 0.0,
        }
    )

    for path in paths:
        try:
            with fs.open(path, "r") as f:
                row = json.load(f)
        except Exception:
            continue

        if not row.get("measured_counterfactual"):
            continue

        primary = row.get("primary") or {}
        secondary = row.get("secondary") or {}

        pkey = identity(primary.get("provider", "unknown"), primary.get("gpu_id"))
        skey = identity(secondary.get("provider", "unknown"), secondary.get("gpu_id"))

        out[pkey]["paired_observations"] += 1
        out[skey]["paired_observations"] += 1

        winner = row.get("winner")
        if winner == "primary":
            out[pkey]["paired_wins"] += 1
            out[skey]["paired_losses"] += 1
        elif winner == "secondary":
            out[skey]["paired_wins"] += 1
            out[pkey]["paired_losses"] += 1

    return dict(out)


def count_paired_probes(bucket: str, workload: str) -> int:
    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))
    return len(
        fs.glob(
            f"hf://buckets/{bucket}/router-evaluation/{workload}/paired/*.json"
        )
    )


def read_promotion_report(
    bucket: str,
    workload: str,
) -> dict[str, Any] | None:
    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))
    path = (
        f"hf://buckets/{bucket}/router-evaluation/"
        f"{workload}/promotion-report.json"
    )

    if not fs.exists(path):
        return None

    try:
        with fs.open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None
