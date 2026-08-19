from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    mean_absolute_error,
)


def editorial_metrics(
    references: pd.DataFrame,
    predictions: pd.DataFrame,
) -> dict[str, Any]:
    df = references.merge(
        predictions,
        on="segment_id",
        suffixes=("_ref", "_pred"),
    )

    y_true = df["editor_label"].astype(str)
    y_pred = df["pred_label"].astype(str)

    metrics = {
        "samples": int(len(df)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(
            f1_score(y_true, y_pred, average="macro", zero_division=0)
        ),
        "keep_recall": float(
            recall_score(
                y_true == "KEEP",
                y_pred == "KEEP",
                zero_division=0,
            )
        ),
        "cut_precision": float(
            precision_score(
                y_true == "CUT",
                y_pred == "CUT",
                zero_division=0,
            )
        ),
        "cut_recall": float(
            recall_score(
                y_true == "CUT",
                y_pred == "CUT",
                zero_division=0,
            )
        ),
        "cut_f1": float(
            f1_score(
                y_true == "CUT",
                y_pred == "CUT",
                zero_division=0,
            )
        ),
        "classification_report": classification_report(
            y_true,
            y_pred,
            output_dict=True,
            zero_division=0,
        ),
    }

    if {
        "importance_label",
        "importance_pred",
    }.issubset(df.columns):
        metrics["importance_mae"] = float(
            mean_absolute_error(
                df["importance_label"],
                df["importance_pred"],
            )
        )

    return metrics
