#!/usr/bin/env python3

import argparse
import pandas as pd

from audio_editorial.features.acoustics import extract_segment_features


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--segments", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sample-rate", type=int, default=16000)
    args = parser.parse_args()

    segments = pd.read_parquet(args.segments)

    features = extract_segment_features(
        args.audio,
        segments,
        sample_rate=args.sample_rate,
    )

    features.to_parquet(args.output, index=False)


if __name__ == "__main__":
    main()
