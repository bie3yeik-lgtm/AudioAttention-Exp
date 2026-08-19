#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

import pandas as pd
from huggingface_hub import HfFileSystem


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", required=True)
    p.add_argument("--output")
    args = p.parse_args()

    fs = HfFileSystem()
    paths = fs.glob(f"hf://buckets/{args.bucket}/runs/*/cost.json")

    rows = []
    for path in paths:
        with fs.open(path, "r") as f:
            rows.append(json.load(f))

    if not rows:
        print("No cost records found.")
        return

    df = pd.DataFrame(rows)

    cols = [
        "provider",
        "workload",
        "estimated_cost_usd",
        "runtime_seconds",
        "input_audio_hours",
        "epochs",
        "samples",
        "cost_per_input_audio_hour_usd",
        "cost_per_epoch_usd",
        "cost_per_1k_samples_usd",
    ]

    print(
        df[[c for c in cols if c in df.columns]]
        .groupby(["provider", "workload"], dropna=False)
        .agg(
            runs=("estimated_cost_usd", "count"),
            total_cost_usd=("estimated_cost_usd", "sum"),
            avg_cost_usd=("estimated_cost_usd", "mean"),
            total_runtime_seconds=("runtime_seconds", "sum"),
        )
        .reset_index()
        .to_string(index=False)
    )

    if args.output:
        df.to_parquet(args.output, index=False)


if __name__ == "__main__":
    main()
