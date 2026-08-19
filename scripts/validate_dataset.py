#!/usr/bin/env python3

import argparse
import json

import pandas as pd


REQUIRED = {
    "segment_id",
    "start_sec",
    "end_sec",
    "text",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    df = pd.read_parquet(args.input)

    missing = sorted(REQUIRED - set(df.columns))
    duplicate_ids = int(df["segment_id"].duplicated().sum()) if "segment_id" in df else -1

    invalid_time = 0
    if {"start_sec", "end_sec"}.issubset(df.columns):
        invalid_time = int((df["end_sec"] < df["start_sec"]).sum())

    report = {
        "rows": int(len(df)),
        "missing_columns": missing,
        "duplicate_segment_ids": duplicate_ids,
        "invalid_time_ranges": invalid_time,
        "valid": not missing and duplicate_ids == 0 and invalid_time == 0,
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    if not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
