from __future__ import annotations

import json
import os
from typing import Any

import yaml
from huggingface_hub import HfFileSystem

from calibration import interval


def group_key(
    *,
    workload: str,
    provider: str,
    gpu_id: str,
    fields: list[str],
) -> str:
    values = {
        "workload": workload,
        "provider": provider,
        "gpu_id": gpu_id,
    }
    return "|".join(
        f"{field}={values.get(field, 'unknown')}"
        for field in fields
    )


class ConformalCalibration:
    def __init__(self, payload: dict[str, Any], cfg: dict[str, Any]):
        self.payload = payload
        self.cfg = cfg

    @classmethod
    def load_latest(
        cls,
        bucket: str,
        *,
        config_path: str = "configs/conformal-router.yaml",
    ) -> "ConformalCalibration":
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))
        rcfg = cfg["registry"]

        latest_path = (
            f"hf://buckets/{bucket}/{rcfg['prefix']}/latest.json"
        )
        with fs.open(latest_path, "r") as f:
            latest = json.load(f)

        with fs.open(latest["calibration_path"], "r") as f:
            payload = json.load(f)

        return cls(payload, cfg)

    def bounds(
        self,
        *,
        workload: str,
        provider: str,
        gpu_id: str,
        predicted_cost_usd: float,
        predicted_runtime_seconds: float,
    ) -> dict[str, Any]:
        fields = self.payload["group_by"]
        key = group_key(
            workload=workload,
            provider=provider,
            gpu_id=gpu_id,
            fields=fields,
        )

        group = self.payload["groups"].get(key)
        source = "group" if group else "global"
        cal = group or self.payload["global"]

        icfg = self.cfg["interval"]

        cost_lower, cost_upper, cost_half = interval(
            predicted_cost_usd,
            cal["cost_q"],
            clamp_lower_to_zero=bool(
                icfg["clamp_lower_to_zero"]
            ),
            max_relative_half_width=float(
                icfg["max_relative_half_width"]
            ),
        )

        runtime_lower, runtime_upper, runtime_half = interval(
            predicted_runtime_seconds,
            cal["runtime_q"],
            clamp_lower_to_zero=True,
            max_relative_half_width=float(
                icfg["max_relative_half_width"]
            ),
        )

        return {
            "coverage_target": self.payload["coverage"],
            "calibration_source": source,
            "calibration_group_key": key,
            "calibration_records": cal["records"],

            "cost_lower_usd": cost_lower,
            "cost_upper_usd": cost_upper,
            "cost_half_width_usd": cost_half,

            "runtime_lower_seconds": runtime_lower,
            "runtime_upper_seconds": runtime_upper,
            "runtime_half_width_seconds": runtime_half,
        }
