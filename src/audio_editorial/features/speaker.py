from __future__ import annotations

import pandas as pd


def attach_speaker_segments(
    segments: pd.DataFrame,
    diarization: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Attach speaker labels to ASR segments.

    Expected diarization schema:
      start_sec, end_sec, speaker_id

    If diarization is None or empty, speaker_id is set to "speaker_0".
    """
    out = segments.copy()

    if diarization is None or diarization.empty:
        out["speaker_id"] = "speaker_0"
        return out

    speakers = []

    for row in out.itertuples(index=False):
        best_speaker = "unknown"
        best_overlap = 0.0

        for d in diarization.itertuples(index=False):
            overlap = max(
                0.0,
                min(float(row.end_sec), float(d.end_sec))
                - max(float(row.start_sec), float(d.start_sec)),
            )
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = str(d.speaker_id)

        speakers.append(best_speaker)

    out["speaker_id"] = speakers
    return out
