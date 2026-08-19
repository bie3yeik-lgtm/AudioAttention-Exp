#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import yaml
from huggingface_hub import HfFileSystem

from calibration import conformal_quantile


def parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def load_json(fs, path):
    try:
        with fs.open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def group_key(row: dict[str, Any], fields: list[str]) -> str:
    parts = []
    for field in fields:
        if field == "workload":
            value = row.get("workload", "unknown")
        elif field == "provider":
            value = row.get("actual", {}).get("provider", "unknown")
        elif field == "gpu_id":
            value = row.get("actual", {}).get("gpu_id", "unknown")
        else:
            value = "unknown"
        parts.append(f"{field}={value}")
    return "|".join(parts)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", default=os.environ.get("HF_BUCKET"))
    p.add_argument("--config", default="configs/conformal-router.yaml")
    args = p.parse_args()

    if not args.bucket:
        raise RuntimeError("HF_BUCKET or --bucket is required")

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    ccfg = cfg["calibration"]
    coverage = float(ccfg["coverage"])
    group_fields = list(ccfg["group_by"])

    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))
    paths = fs.glob(
        f"hf://buckets/{args.bucket}/runs/*/contextual-evaluation.json"
    )

    cutoff = datetime.now(timezone.utc) - timedelta(
        days=int(ccfg["recency_days"])
    )

    rows = []

    for path in paths[-int(ccfg["max_records"]):]:
        row = load_json(fs, path)
        if not row or not row.get("evaluable"):
            continue

        contextual = row.get("contextual") or {}
        actual = row.get("actual") or {}

        if not contextual.get("same_route"):
            continue

        predicted_cost = contextual.get("predicted_cost_usd")
        actual_cost = actual.get("cost_usd")

        predicted_runtime = contextual.get("predicted_runtime_seconds")
        actual_runtime = actual.get("runtime_seconds")

        if None in (
            predicted_cost,
            actual_cost,
            predicted_runtime,
            actual_runtime,
        ):
            continue

        cost_path = (
            f"hf://buckets/{args.bucket}/runs/{row['job_id']}/cost.json"
        )
        cost = load_json(fs, cost_path)
        observed = parse_dt(
            (cost or {}).get("observed_terminal_at")
        )
        if observed and observed < cutoff:
            continue

        row = dict(row)
        row["_cost_abs_residual"] = abs(
            float(actual_cost) - float(predicted_cost)
        )
        row["_runtime_abs_residual"] = abs(
            float(actual_runtime) - float(predicted_runtime)
        )
        rows.append(row)

    min_records = int(ccfg["min_calibration_records"])
    if len(rows) < min_records:
        raise RuntimeError(
            f"Not enough conformal calibration records: "
            f"{len(rows)} < {min_records}"
        )

    global_cost = [r["_cost_abs_residual"] for r in rows]
    global_runtime = [r["_runtime_abs_residual"] for r in rows]

    finite = bool(ccfg["finite_sample_correction"])

    global_calibration = {
        "records": len(rows),
        "cost_q": conformal_quantile(
            global_cost,
            coverage=coverage,
            finite_sample_correction=finite,
        ),
        "runtime_q": conformal_quantile(
            global_runtime,
            coverage=coverage,
            finite_sample_correction=finite,
        ),
    }

    grouped = defaultdict(list)
    for row in rows:
        grouped[group_key(row, group_fields)].append(row)

    groups = {}
    min_group = int(ccfg["min_group_records"])

    for key, grows in grouped.items():
        if len(grows) < min_group:
            continue

        groups[key] = {
            "records": len(grows),
            "cost_q": conformal_quantile(
                [r["_cost_abs_residual"] for r in grows],
                coverage=coverage,
                finite_sample_correction=finite,
            ),
            "runtime_q": conformal_quantile(
                [r["_runtime_abs_residual"] for r in grows],
                coverage=coverage,
                finite_sample_correction=finite,
            ),
        }

    payload = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "coverage": coverage,
        "group_by": group_fields,
        "global": global_calibration,
        "groups": groups,
        "config": cfg,
    }

    rcfg = cfg["registry"]
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = f"{rcfg['prefix']}/{version}"

    calibration_path = (
        f"hf://buckets/{args.bucket}/{prefix}/"
        f"{rcfg['calibration_file']}"
    )
    metadata_path = (
        f"hf://buckets/{args.bucket}/{prefix}/"
        f"{rcfg['metadata_file']}"
    )

    fs.makedirs(calibration_path.rsplit("/", 1)[0], exist_ok=True)

    with fs.open(calibration_path, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with fs.open(metadata_path, "w") as f:
        json.dump(
            {
                "schema_version": "1.0",
                "version": version,
                "created_at": payload["created_at"],
                "records": len(rows),
                "coverage": coverage,
                "group_count": len(groups),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    latest_path = (
        f"hf://buckets/{args.bucket}/{rcfg['prefix']}/latest.json"
    )
    fs.makedirs(latest_path.rsplit("/", 1)[0], exist_ok=True)

    with fs.open(latest_path, "w") as f:
        json.dump(
            {
                "version": version,
                "prefix": prefix,
                "calibration_path": calibration_path,
                "metadata_path": metadata_path,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
