from __future__ import annotations

import pandas as pd


def merge_artifacts(
    asr: pd.DataFrame,
    features: pd.DataFrame,
    teacher: pd.DataFrame,
) -> pd.DataFrame:
    df = asr.merge(features, on="segment_id", how="left")
    df = df.merge(teacher, on="segment_id", how="left")
    return df
