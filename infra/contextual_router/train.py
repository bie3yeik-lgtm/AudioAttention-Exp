#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from catboost import CatBoostRegressor
from huggingface_hub import HfFileSystem
from sklearn.metrics import mean_absolute_error, mean_squared_error

from dataset import load_training_frame
from features import normalize_frame


def load_yaml(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def metrics(y_true, y_pred) -> dict[str, float]:
    rmse = math.sqrt(mean_squared_error(y_true, y_pred))
    mae = mean_absolute_error(y_true, y_pred)

    denom = np.maximum(np.abs(np.asarray(y_true, dtype=float)), 1e-9)
    mape = float(
        np.mean(np.abs(np.asarray(y_pred) - np.asarray(y_true)) / denom)
    )

    return {
        "rmse": float(rmse),
        "mae": float(mae),
        "mape": mape,
    }


def upload_file(fs: HfFileSystem, local: Path, remote: str) -> None:
    parent = remote.rsplit("/", 1)[0]
    fs.makedirs(parent, exist_ok=True)
    with local.open("rb") as src, fs.open(remote, "wb") as dst:
        shutil.copyfileobj(src, dst)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", default=os.environ.get("HF_BUCKET"))
    p.add_argument("--config", default="configs/contextual-router.yaml")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not args.bucket:
        raise RuntimeError("HF_BUCKET or --bucket is required")

    cfg = load_yaml(args.config)

    dcfg = cfg["dataset"]
    fcfg = cfg["features"]
    tcfg = cfg["training"]
    rcfg = cfg["registry"]

    df = load_training_frame(
        args.bucket,
        recency_days=int(dcfg["recency_days"]),
        max_records=int(dcfg["max_records"]),
    )

    min_records = int(dcfg["min_records_to_train"])
    if len(df) < min_records:
        raise RuntimeError(
            f"Not enough contextual training records: {len(df)} < {min_records}"
        )

    categorical = list(fcfg["categorical"])
    numerical = list(fcfg["numerical"])
    feature_cols = categorical + numerical

    df = normalize_frame(
        df,
        categorical=categorical,
        numerical=numerical,
    )

    valid_fraction = float(dcfg["validation_fraction"])
    split = max(1, int(len(df) * (1.0 - valid_fraction)))
    split = min(split, len(df) - 1)

    train_df = df.iloc[:split].copy()
    valid_df = df.iloc[split:].copy()

    X_train = train_df[feature_cols]
    X_valid = valid_df[feature_cols]

    common = dict(
        iterations=int(tcfg["iterations"]),
        depth=int(tcfg["depth"]),
        learning_rate=float(tcfg["learning_rate"]),
        l2_leaf_reg=float(tcfg["l2_leaf_reg"]),
        random_seed=int(tcfg["random_seed"]),
        verbose=False,
        allow_writing_files=False,
    )

    runtime_model = CatBoostRegressor(
        **common,
        loss_function=str(tcfg["loss_function_runtime"]),
    )
    runtime_model.fit(
        X_train,
        train_df["runtime_seconds"],
        cat_features=categorical,
        eval_set=(X_valid, valid_df["runtime_seconds"]),
        early_stopping_rounds=int(tcfg["early_stopping_rounds"]),
        verbose=False,
    )

    cost_model = CatBoostRegressor(
        **common,
        loss_function=str(tcfg["loss_function_cost"]),
    )
    cost_model.fit(
        X_train,
        train_df["estimated_cost_usd"],
        cat_features=categorical,
        eval_set=(X_valid, valid_df["estimated_cost_usd"]),
        early_stopping_rounds=int(tcfg["early_stopping_rounds"]),
        verbose=False,
    )

    runtime_pred = runtime_model.predict(X_valid)
    cost_pred = cost_model.predict(X_valid)

    runtime_metrics = metrics(valid_df["runtime_seconds"], runtime_pred)
    cost_metrics = metrics(valid_df["estimated_cost_usd"], cost_pred)

    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = f"{rcfg['prefix']}/{version}"

    metadata = {
        "schema_version": "1.0",
        "model_version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "records_total": len(df),
        "records_train": len(train_df),
        "records_validation": len(valid_df),
        "features": {
            "categorical": categorical,
            "numerical": numerical,
            "ordered": feature_cols,
        },
        "runtime_metrics": runtime_metrics,
        "cost_metrics": cost_metrics,
        "config": cfg,
    }

    print(json.dumps(metadata, ensure_ascii=False, indent=2))

    if args.dry_run:
        return

    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        runtime_file = td / rcfg["runtime_model_file"]
        cost_file = td / rcfg["cost_model_file"]
        metadata_file = td / rcfg["metadata_file"]

        runtime_model.save_model(str(runtime_file))
        cost_model.save_model(str(cost_file))
        metadata_file.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        upload_file(
            fs,
            runtime_file,
            f"hf://buckets/{args.bucket}/{prefix}/{rcfg['runtime_model_file']}",
        )
        upload_file(
            fs,
            cost_file,
            f"hf://buckets/{args.bucket}/{prefix}/{rcfg['cost_model_file']}",
        )
        upload_file(
            fs,
            metadata_file,
            f"hf://buckets/{args.bucket}/{prefix}/{rcfg['metadata_file']}",
        )

        latest = {
            "model_version": version,
            "prefix": prefix,
            "metadata": metadata,
        }

        latest_path = (
            f"hf://buckets/{args.bucket}/{rcfg['prefix']}/latest.json"
        )
        fs.makedirs(latest_path.rsplit("/", 1)[0], exist_ok=True)
        with fs.open(latest_path, "w") as f:
            json.dump(latest, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
