from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def transcribe_audio(
    audio_path: str,
    model_id: str = "nvidia/parakeet-tdt_ctc-0.6b-ja",
    session_id: str | None = None,
) -> pd.DataFrame:
    import nemo.collections.asr as nemo_asr

    model = nemo_asr.models.ASRModel.from_pretrained(model_id)

    session_id = session_id or Path(audio_path).stem

    results = model.transcribe([audio_path], timestamps=True)

    if not results:
        raise RuntimeError("Parakeet returned no transcription.")

    hyp: Any = results[0]

    text = getattr(hyp, "text", str(hyp))

    timestamps = getattr(hyp, "timestamp", None)
    segments = []

    if isinstance(timestamps, dict) and timestamps.get("segment"):
        for i, seg in enumerate(timestamps["segment"]):
            segments.append(
                {
                    "session_id": session_id,
                    "segment_id": f"{session_id}:{i:06d}",
                    "start_sec": float(seg.get("start", 0.0)),
                    "end_sec": float(seg.get("end", 0.0)),
                    "text": str(seg.get("segment", seg.get("text", ""))),
                    "confidence": 1.0,
                    "tdt_text": str(seg.get("segment", seg.get("text", ""))),
                    "ctc_text": None,
                }
            )
    else:
        segments.append(
            {
                "session_id": session_id,
                "segment_id": f"{session_id}:000000",
                "start_sec": 0.0,
                "end_sec": 0.0,
                "text": text,
                "confidence": 1.0,
                "tdt_text": text,
                "ctc_text": None,
            }
        )

    return pd.DataFrame(segments)
