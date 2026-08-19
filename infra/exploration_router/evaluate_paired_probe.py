#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os

from huggingface_hub import HfFileSystem


def read_json(fs, path: str):
    with fs.open(path, "r") as f:
        return json.load(f)


def normalized_cost(record: dict) -> float:
    workload = record["workload"]
    cost = float(record["estimated_cost_usd"])

    if workload == "teacher":
        units = float(record["input_audio_hours"])
    elif workload == "student":
        units = float(record["epochs"])
    else:
        units = 1.0

    if units <= 0:
        raise RuntimeError("Invalid accounting units")

    return cost / units


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", required=True)
    p.add_argument("--probe-id", required=True)
    p.add_argument("--primary-job-id", required=True)
    p.add_argument("--secondary-job-id", required=True)
    args = p.parse_args()

    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))

    a = read_json(
        fs,
        f"hf://buckets/{args.bucket}/runs/{args.primary_job_id}/cost.json",
    )
    b = read_json(
        fs,
        f"hf://buckets/{args.bucket}/runs/{args.secondary_job_id}/cost.json",
    )

    if a["workload"] != b["workload"]:
        raise RuntimeError("Paired jobs have different workloads")

    ca = normalized_cost(a)
    cb = normalized_cost(b)

    winner = "primary" if ca <= cb else "secondary"

    out = {
        "schema_version": "1.0",
        "probe_id": args.probe_id,
        "workload": a["workload"],
        "primary": {
            "job_id": args.primary_job_id,
            "provider": a["provider"],
            "gpu_id": a.get("gpu_id") or a.get("flavor"),
            "normalized_cost_usd_per_unit": ca,
            "estimated_cost_usd": a["estimated_cost_usd"],
        },
        "secondary": {
            "job_id": args.secondary_job_id,
            "provider": b["provider"],
            "gpu_id": b.get("gpu_id") or b.get("flavor"),
            "normalized_cost_usd_per_unit": cb,
            "estimated_cost_usd": b["estimated_cost_usd"],
        },
        "winner": winner,
        "absolute_unit_cost_difference_usd": abs(ca - cb),
        "primary_minus_secondary_unit_cost_usd": ca - cb,
        "measured_counterfactual": True,
    }

    path = (
        f"hf://buckets/{args.bucket}/router-evaluation/"
        f"{a['workload']}/paired/{args.probe_id}.json"
    )
    fs.makedirs(path.rsplit("/", 1)[0], exist_ok=True)
    with fs.open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
