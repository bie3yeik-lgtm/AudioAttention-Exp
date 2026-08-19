#!/usr/bin/env python3
"""
Add GPU/flavor identity to a cost.json record.

Historical routing requires provider + hardware identity, not only provider.
"""

from __future__ import annotations

import argparse
import json
import os

from huggingface_hub import HfFileSystem


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", required=True)
    p.add_argument("--job-id", required=True)
    p.add_argument("--gpu-id")
    p.add_argument("--flavor")
    args = p.parse_args()

    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))
    path = f"hf://buckets/{args.bucket}/runs/{args.job_id}/cost.json"

    with fs.open(path, "r") as f:
        record = json.load(f)

    if args.gpu_id:
        record["gpu_id"] = args.gpu_id

    if args.flavor:
        record["flavor"] = args.flavor

    with fs.open(path, "w") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
