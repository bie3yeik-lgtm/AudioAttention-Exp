#!/usr/bin/env python3

import argparse
import json

import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    mean_absolute_error,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--references", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    pred = pd.read_parquet(args.predictions)
    ref = pd.read_parquet(args.references)

    df = ref.merge(
        pred,
        on="segment_id",
        suffixes=("_ref", "_pred"),
    )

    pred_keep_col = (
        "keep_recommendation_pred"
        if "keep_recommendation_pred" in df.columns
        else "keep_recommendation"
    )

    ref_keep_col = (
        "editor_label"
        if "editor_label" in df.columns
        else "keep_recommendation_ref"
    )

    pred_importance_col = (
        "importance_pred"
        if "importance_pred" in df.columns
        else "importance"
    )

    ref_importance_col = (
        "importance_label"
        if "importance_label" in df.columns
        else "importance_ref"
    )

    metrics = {
        "samples": int(len(df)),
        "keep_accuracy": float(
            accuracy_score(
                df[ref_keep_col].astype(str),
                df[pred_keep_col].astype(str),
            )
        ),
        "importance_mae": float(
            mean_absolute_error(
                df[ref_importance_col].astype(float),
                df[pred_importance_col].astype(float),
            )
        ),
        "keep_report": classification_report(
            df[ref_keep_col].astype(str),
            df[pred_keep_col].astype(str),
            output_dict=True,
            zero_division=0,
        ),
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
