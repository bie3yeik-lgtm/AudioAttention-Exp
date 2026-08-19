#!/usr/bin/env python3

import argparse
import pandas as pd

from audio_editorial.features.merge import merge_artifacts


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--asr", required=True)
    parser.add_argument("--features", required=True)
    parser.add_argument("--teacher", required=True)
    parser.add_argument("--output", required=True)

    args = parser.parse_args()

    asr = pd.read_parquet(args.asr)
    features = pd.read_parquet(args.features)
    teacher = pd.read_parquet(args.teacher)

    merged = merge_artifacts(
        asr=asr,
        features=features,
        teacher=teacher,
    )

    merged.to_parquet(args.output, index=False)


if __name__ == "__main__":
    main()
