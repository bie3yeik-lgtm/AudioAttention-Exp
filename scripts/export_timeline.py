#!/usr/bin/env python3

import argparse
import json

import pandas as pd

from audio_editorial.models.timeline import (
    TimelineConfig,
    build_timeline,
)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", required=True)

    parser.add_argument(
        "--cut-threshold",
        type=float,
        default=0.70,
    )

    parser.add_argument(
        "--optional-threshold",
        type=float,
        default=0.45,
    )

    args = parser.parse_args()

    df = pd.read_parquet(args.predictions)

    edits = build_timeline(
        df,
        TimelineConfig(
            cut_threshold=args.cut_threshold,
            optional_threshold=args.optional_threshold,
        ),
    )

    result = {
        "schema_version": "1.0",
        "edits": edits,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2,
        )


if __name__ == "__main__":
    main()
