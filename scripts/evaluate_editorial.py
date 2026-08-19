#!/usr/bin/env python3

import argparse
import json

import pandas as pd

from audio_editorial.evaluation.metrics import editorial_metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--references", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    predictions = pd.read_parquet(args.predictions)
    references = pd.read_parquet(args.references)

    metrics = editorial_metrics(
        references=references,
        predictions=predictions,
    )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
