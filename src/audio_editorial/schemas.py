from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


DialogueRole = Literal[
    "question",
    "answer",
    "explanation",
    "example",
    "summary",
    "transition",
    "filler",
    "repetition",
    "digression",
    "other",
]

EditorialAction = Literal["KEEP", "OPTIONAL", "CUT"]


class ASRSegment(BaseModel):
    session_id: str
    segment_id: str
    start_sec: float
    end_sec: float
    text: str
    confidence: float = 1.0
    tdt_text: Optional[str] = None
    ctc_text: Optional[str] = None


class AcousticFeatures(BaseModel):
    segment_id: str
    rms_db: float
    peak_db: float
    pitch_mean: float
    pitch_std: float
    spectral_centroid: float
    spectral_bandwidth: float
    speech_rate: float = 0.0
    silence_before_ms: float = 0.0
    silence_after_ms: float = 0.0
    relative_loudness_z: float = 0.0
    speaker_id: Optional[str] = None


class TeacherLabel(BaseModel):
    segment_id: str
    summary: str = ""
    topic: str = ""
    dialogue_role: DialogueRole = "other"
    importance: float = Field(ge=0.0, le=1.0)
    emphasis: float = Field(ge=0.0, le=1.0)
    novelty: float = Field(ge=0.0, le=1.0)
    redundancy: float = Field(ge=0.0, le=1.0)
    filler: float = Field(ge=0.0, le=1.0)
    speaker_intent: str = ""
    keep_recommendation: EditorialAction


class TimelineEdit(BaseModel):
    start: float
    end: float
    action: EditorialAction
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
