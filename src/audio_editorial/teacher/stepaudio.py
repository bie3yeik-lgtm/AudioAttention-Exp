from __future__ import annotations

import json
import re
from typing import Any

import torch
from transformers import AutoModelForCausalLM

from audio_editorial.schemas import TeacherLabel
from audio_editorial.teacher.prompts import SYSTEM_PROMPT, build_segment_prompt


class StepAudioTeacher:
    def __init__(
        self,
        model_id: str = "stepfun-ai/Step-Audio-2-mini",
        device_map: str = "auto",
    ) -> None:
        self.model_id = model_id
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            trust_remote_code=True,
            torch_dtype="auto",
            device_map=device_map,
        )

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))

    def analyze(
        self,
        audio_path: str,
        segment_id: str,
        transcript: str,
        previous_context: str = "",
        next_context: str = "",
        global_summary: str = "",
        max_new_tokens: int = 512,
    ) -> TeacherLabel:
        prompt = build_segment_prompt(
            transcript=transcript,
            previous_context=previous_context,
            next_context=next_context,
            global_summary=global_summary,
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "human",
                "content": [
                    {"type": "audio", "audio": audio_path},
                    {"type": "text", "text": prompt},
                ],
            },
            {"role": "assistant", "content": None},
        ]

        _, text, _ = self.model(
            messages,
            max_new_tokens=max_new_tokens,
            temperature=0.1,
            do_sample=False,
        )

        payload = self._extract_json(text)
        payload["segment_id"] = segment_id
        return TeacherLabel.model_validate(payload)
