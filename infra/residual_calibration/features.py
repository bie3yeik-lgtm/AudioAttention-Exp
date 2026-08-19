from __future__ import annotations

import pandas as pd


def normalize_frame(
    df: pd.DataFrame,
    *,
    categorical: list[str],
    numerical: list[str],
) -> pd.DataFrame:
    df = df.copy()

    for col in categorical:
        if col not in df.columns:
            df[col] = "unknown"
        df[col] = df[col].fillna("unknown").astype(str)

    for col in numerical:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df
