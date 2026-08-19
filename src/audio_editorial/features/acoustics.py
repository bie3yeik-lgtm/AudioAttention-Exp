from __future__ import annotations

import math

import librosa
import numpy as np
import pandas as pd


EPS = 1e-10


def _db(value: float) -> float:
    return 20.0 * math.log10(max(value, EPS))


def extract_segment_features(
    audio_path: str,
    segments: pd.DataFrame,
    sample_rate: int = 16000,
) -> pd.DataFrame:
    y, sr = librosa.load(audio_path, sr=sample_rate, mono=True)

    rows = []

    for row in segments.itertuples(index=False):
        start = max(0, int(float(row.start_sec) * sr))
        end = min(len(y), int(float(row.end_sec) * sr))

        if end <= start:
            clip = np.zeros(max(1, sr // 10), dtype=np.float32)
        else:
            clip = y[start:end]

        rms = float(np.sqrt(np.mean(np.square(clip))) + EPS)
        peak = float(np.max(np.abs(clip)) + EPS)

        centroid = librosa.feature.spectral_centroid(y=clip, sr=sr)
        bandwidth = librosa.feature.spectral_bandwidth(y=clip, sr=sr)

        try:
            f0 = librosa.yin(
                clip,
                fmin=60.0,
                fmax=500.0,
                sr=sr,
            )
            f0 = f0[np.isfinite(f0)]
            pitch_mean = float(np.mean(f0)) if len(f0) else 0.0
            pitch_std = float(np.std(f0)) if len(f0) else 0.0
        except Exception:
            pitch_mean = 0.0
            pitch_std = 0.0

        text = str(getattr(row, "text", ""))
        duration = max(float(row.end_sec) - float(row.start_sec), 1e-6)
        speech_rate = len(text) / duration

        rows.append(
            {
                "segment_id": row.segment_id,
                "rms_db": _db(rms),
                "peak_db": _db(peak),
                "pitch_mean": pitch_mean,
                "pitch_std": pitch_std,
                "spectral_centroid": float(np.mean(centroid)),
                "spectral_bandwidth": float(np.mean(bandwidth)),
                "speech_rate": float(speech_rate),
                "silence_before_ms": 0.0,
                "silence_after_ms": 0.0,
                "speaker_id": getattr(row, "speaker_id", None),
            }
        )

    df = pd.DataFrame(rows)

    if len(df):
        mu = float(df["rms_db"].mean())
        sigma = float(df["rms_db"].std(ddof=0))
        if sigma < 1e-6:
            sigma = 1.0
        df["relative_loudness_z"] = (df["rms_db"] - mu) / sigma
    else:
        df["relative_loudness_z"] = []

    return df
