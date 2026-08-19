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
import yaml
from catboost import CatBoostRegressor
from huggingface_hub import HfFileSystem
from sklearn.metrics import mean_absolute_error, mean_squared_error

from dataset import load_residual_frame
from features import normalize_frame


def load_yaml(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def metric(y_true, y_pred) -> dict[str, float]:
    rmse = math.sqrt(mean_squared_error(y_true, y_pred))
    mae = mean_absolute_error(y_true, y_pred)
    return {"rmse": float(rmse), "mae": float(mae)}


def upload(fs: HfFileSystem, local: Path, remote: str) -> None:
    fs.makedirs(remote.rsplit("/", 1)[0], exist_ok=True)
    with local.open("rb") as src, fs.open(remote, "wb") as dst:
        shutil.copyfileobj(src, dst)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", default=os.environ.get("HF_BUCKET"))
    p.add_argument(
        "--config",
        default="configs/residual-calibration.yaml",
    )
    args = p.parse_args()

    if not args.bucket:
        raise RuntimeError("HF_BUCKET or --bucket is required")

    cfg = load_yaml(args.config)
    dcfg = cfg["dataset"]
    fcfg = cfg["features"]
    tcfg = cfg["training"]
    rcfg = cfg["registry"]

    df = load_residual_frame(
        args.bucket,
        recency_days=int(dcfg["recency_days"]),
        max_records=int(dcfg["max_records"]),
    )

    min_eval = int(dcfg["min_evaluations"])
    if len(df) < min_eval:
        raise RuntimeError(
            f"Not enough residual evaluations: {len(df)} < {min_eval}"
        )

    cat_cols = list(fcfg["categorical"])
    num_cols = list(fcfg["numerical"])
    feature_cols = cat_cols + num_cols

    df = normalize_frame(
        df,
        categorical=cat_cols,
        numerical=num_cols,
    )

    split = max(
        1,
        int(len(df) * (1.0 - float(dcfg["validation_fraction"]))),
    )
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
        loss_function="RMSE",
    )

    cost_model = CatBoostRegressor(**common)
    cost_model.fit(
        X_train,
        train_df["contextual_cost_ape"],
        cat_features=cat_cols,
        eval_set=(X_valid, valid_df["contextual_cost_ape"]),
        early_stopping_rounds=int(tcfg["early_stopping_rounds"]),
        verbose=False,
    )

    runtime_model = CatBoostRegressor(**common)
    runtime_model.fit(
        X_train,
        train_df["contextual_runtime_ape"],
        cat_features=cat_cols,
        eval_set=(X_valid, valid_df["contextual_runtime_ape"]),
        early_stopping_rounds=int(tcfg["early_stopping_rounds"]),
        verbose=False,
    )

    cost_pred = np.maximum(
        0.0,
        cost_model.predict(X_valid),
    )
    runtime_pred = np.maximum(
        0.0,
        runtime_model.predict(X_valid),
    )

    metadata = {
        "schema_version": "1.0",
        "model_version": datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "records_total": len(df),
        "records_train": len(train_df),
        "records_validation": len(valid_df),
        "features": {
            "categorical": cat_cols,
            "numerical": num_cols,
            "ordered": feature_cols,
        },
        "cost_ape_metrics": metric(
            valid_df["contextual_cost_ape"],
            cost_pred,
        ),
        "runtime_ape_metrics": metric(
            valid_df["contextual_runtime_ape"],
            runtime_pred,
        ),
        "config": cfg,
    }

    version = metadata["model_version"]
    prefix = f"{rcfg['prefix']}/{version}"

    fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        cost_file = td / rcfg["cost_error_model_file"]
        runtime_file = td / rcfg["runtime_error_model_file"]
        meta_file = td / rcfg["metadata_file"]

        cost_model.save_model(str(cost_file))
        runtime_model.save_model(str(runtime_file))
        meta_file.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        upload(
            fs,
            cost_file,
            f"hf://buckets/{args.bucket}/{prefix}/"
            f"{rcfg['cost_error_model_file']}",
        )
        upload(
            fs,
            runtime_file,
            f"hf://buckets/{args.bucket}/{prefix}/"
            f"{rcfg['runtime_error_model_file']}",
        )
        upload(
            fs,
            meta_file,
            f"hf://buckets/{args.bucket}/{prefix}/"
            f"{rcfg['metadata_file']}",
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

    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
