from __future__ import annotations

import json
import os
from typing import Any

from huggingface_hub import HfFileSystem


def read_contextual_promotion(
    bucket: str,
    workload: str,
) -> dict[str, Any] | None:
    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))
    path = (
        f"hf://buckets/{bucket}/router-evaluation/"
        f"{workload}/contextual-promotion-report.json"
    )

    if not fs.exists(path):
        return None

    try:
        with fs.open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def prediction_source(
    bucket: str,
    workload: str,
    *,
    requested: str = "auto",
) -> tuple[str, dict[str, Any] | None, str]:
    """
    requested:
      historical -> always Historical
      contextual -> Contextual only if promoted, else Historical
      auto       -> Contextual iff promoted
    """
    if requested not in {"auto", "historical", "contextual"}:
        raise ValueError(requested)

    report = read_contextual_promotion(bucket, workload)

    if requested == "historical":
        return "historical", report, "explicit_historical"

    promoted = bool(report and report.get("promote_contextual_router"))

    if promoted:
        return "contextual", report, "contextual_promotion_passed"

    return "historical", report, "contextual_not_promoted_fail_closed"
