#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os

from huggingface_hub import HfFileSystem


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", required=True)
    p.add_argument(
        "--prefix",
        default="router-models/contextual/v1",
    )
    args = p.parse_args()

    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))

    latest_path = f"hf://buckets/{args.bucket}/{args.prefix}/latest.json"

    if not fs.exists(latest_path):
        raise SystemExit("No contextual model has been registered yet.")

    with fs.open(latest_path, "r") as f:
        latest = json.load(f)

    metadata = latest["metadata"]

    report = {
        "model_version": metadata["model_version"],
        "created_at": metadata["created_at"],
        "records_total": metadata["records_total"],
        "records_train": metadata["records_train"],
        "records_validation": metadata["records_validation"],
        "runtime_metrics": metadata["runtime_metrics"],
        "cost_metrics": metadata["cost_metrics"],
        "features": metadata["features"],
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
