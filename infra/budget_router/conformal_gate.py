from __future__ import annotations

import json
import os
from typing import Any

from huggingface_hub import HfFileSystem


def read_conformal_promotion(
    bucket: str,
    workload: str,
) -> dict[str, Any] | None:
    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))
    path = (
        f"hf://buckets/{bucket}/router-evaluation/"
        f"{workload}/conformal-promotion-report.json"
    )

    if not fs.exists(path):
        return None

    try:
        with fs.open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def conformal_is_promoted(
    bucket: str,
    workload: str,
) -> tuple[bool, dict[str, Any] | None]:
    report = read_conformal_promotion(bucket, workload)
    promoted = bool(
        report and report.get("promote_conformal_router")
    )
    return promoted, report
