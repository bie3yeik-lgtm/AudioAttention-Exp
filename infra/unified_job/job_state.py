from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

from huggingface_hub import HfFileSystem


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def bucket_path(bucket: str, relative: str) -> str:
    return f"hf://buckets/{bucket}/{relative.lstrip('/')}"


def fs(token: str | None = None) -> HfFileSystem:
    return HfFileSystem(token=token or os.environ.get("HF_TOKEN"))


def write_json(bucket: str, relative: str, payload: dict[str, Any]) -> None:
    hffs = fs()
    path = bucket_path(bucket, relative)
    parent = path.rsplit("/", 1)[0]
    hffs.makedirs(parent, exist_ok=True)
    with hffs.open(path, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def read_json(bucket: str, relative: str) -> dict[str, Any]:
    with fs().open(bucket_path(bucket, relative), "r") as f:
        return json.load(f)


def exists(bucket: str, relative: str) -> bool:
    return fs().exists(bucket_path(bucket, relative))


@dataclass
class CostRecord:
    schema_version: str
    job_id: str
    provider: str
    resource_id: str
    workload: str

    quoted_price_usd_per_hour: float
    provider_reported_price_usd_per_hour: float | None

    launched_at: str
    observed_terminal_at: str
    runtime_seconds: float

    estimated_cost_usd: float

    input_audio_hours: float | None = None
    epochs: int | None = None
    samples: int | None = None

    cost_per_input_audio_hour_usd: float | None = None
    cost_per_epoch_usd: float | None = None
    cost_per_1k_samples_usd: float | None = None

    accounting_method: str = (
        "wall_clock_runtime_seconds * price_snapshot; "
        "estimate only, not provider invoice"
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
