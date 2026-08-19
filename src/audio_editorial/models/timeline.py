from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class TimelineConfig:
    cut_threshold: float = 0.70
    optional_threshold: float = 0.45
    min_cut_duration: float = 0.8
    merge_gap: float = 0.3


def build_timeline(
    predictions: pd.DataFrame,
    config: TimelineConfig | None = None,
) -> list[dict]:
    config = config or TimelineConfig()

    raw = []

    for row in predictions.itertuples(index=False):
        p_cut = float(getattr(row, "p_cut", 0.0))
        p_optional = float(getattr(row, "p_optional", 0.0))

        if p_cut >= config.cut_threshold:
            action = "CUT"
            confidence = p_cut
        elif p_optional >= config.optional_threshold:
            action = "OPTIONAL"
            confidence = p_optional
        else:
            action = "KEEP"
            confidence = float(getattr(row, "p_keep", 1.0))

        raw.append(
            {
                "start": float(row.start_sec),
                "end": float(row.end_sec),
                "action": action,
                "reason": str(getattr(row, "reason", "")),
                "confidence": confidence,
            }
        )

    merged = []

    for item in raw:
        if (
            merged
            and item["action"] == merged[-1]["action"]
            and item["start"] - merged[-1]["end"] <= config.merge_gap
        ):
            merged[-1]["end"] = item["end"]
            merged[-1]["confidence"] = max(
                merged[-1]["confidence"],
                item["confidence"],
            )
        else:
            merged.append(item)

    return [
        item
        for item in merged
        if item["action"] != "CUT"
        or item["end"] - item["start"] >= config.min_cut_duration
    ]
