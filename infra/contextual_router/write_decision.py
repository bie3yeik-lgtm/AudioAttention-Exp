#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os

from huggingface_hub import HfFileSystem


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", required=True)
    p.add_argument("--job-id", required=True)
    p.add_argument("--decision", required=True)
    args = p.parse_args()

    with open(args.decision, "r", encoding="utf-8") as f:
        obj = json.load(f)

    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))
    path = (
        f"hf://buckets/{args.bucket}/runs/"
        f"{args.job_id}/contextual-decision.json"
    )
    fs.makedirs(path.rsplit("/", 1)[0], exist_ok=True)

    with fs.open(path, "w") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

    print(path)


if __name__ == "__main__":
    main()
