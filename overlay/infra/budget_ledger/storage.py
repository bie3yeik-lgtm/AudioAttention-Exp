from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from huggingface_hub import HfFileSystem


def fs() -> HfFileSystem:
    return HfFileSystem(token=os.environ.get("HF_TOKEN"))


def prefix(bucket: str, storage_prefix: str) -> str:
    return f"hf://buckets/{bucket}/{storage_prefix.strip('/')}"


def load_events(bucket: str, storage_prefix: str) -> list[dict[str, Any]]:
    hffs = fs()
    base = prefix(bucket, storage_prefix)
    paths = hffs.glob(f"{base}/events/*/*/*.json")
    rows = []
    for path in paths:
        try:
            with hffs.open(path, "r") as f:
                rows.append(json.load(f))
        except Exception:
            continue
    return rows


def append_event(bucket: str, storage_prefix: str, event: dict[str, Any]) -> str:
    hffs = fs()
    now = datetime.now(timezone.utc)
    event = dict(event)
    event.setdefault("schema_version", "1.0")
    event.setdefault("created_at", now.isoformat())
    event.setdefault("event_id", uuid.uuid4().hex)
    base = prefix(bucket, storage_prefix)
    path = (
        f"{base}/events/{now:%Y}/{now:%m}/"
        f"{now:%Y%m%dT%H%M%S.%fZ}_{event['event_id']}.json"
    )
    hffs.makedirs(path.rsplit("/", 1)[0], exist_ok=True)
    with hffs.open(path, "w") as f:
        json.dump(event, f, ensure_ascii=False, indent=2)
    return path
