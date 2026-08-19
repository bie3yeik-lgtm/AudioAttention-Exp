from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from catboost import CatBoostRegressor
from huggingface_hub import HfFileSystem

from features import normalize_frame


class ResidualCalibrationModel:
    def __init__(
        self,
        cost_model: CatBoostRegressor,
        runtime_model: CatBoostRegressor,
        metadata: dict[str, Any],
    ) -> None:
        self.cost_model = cost_model
        self.runtime_model = runtime_model
        self.metadata = metadata

    @classmethod
    def load_latest(
        cls,
        bucket: str,
        *,
        config_path: str = "configs/residual-calibration.yaml",
    ) -> "ResidualCalibrationModel":
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        rcfg = cfg["registry"]
        fs = HfFileSystem(token=os.environ.get("HF_TOKEN"))

        latest_path = (
            f"hf://buckets/{bucket}/{rcfg['prefix']}/latest.json"
        )

        with fs.open(latest_path, "r") as f:
            latest = json.load(f)

        prefix = latest["prefix"]

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            cost_path = td / "cost_ape.cbm"
            runtime_path = td / "runtime_ape.cbm"

            mapping = [
                (rcfg["cost_error_model_file"], cost_path),
                (rcfg["runtime_error_model_file"], runtime_path),
            ]

            for remote_name, local in mapping:
                remote = (
                    f"hf://buckets/{bucket}/{prefix}/{remote_name}"
                )
                with fs.open(remote, "rb") as src, local.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

            cost_model = CatBoostRegressor()
            cost_model.load_model(str(cost_path))

            runtime_model = CatBoostRegressor()
            runtime_model.load_model(str(runtime_path))

        return cls(
            cost_model=cost_model,
            runtime_model=runtime_model,
            metadata=latest["metadata"],
        )

    def predict(self, rows: list[dict[str, Any]]) -> list[dict[str, float]]:
        feat = self.metadata["features"]
        cat_cols = feat["categorical"]
        num_cols = feat["numerical"]
        ordered = feat["ordered"]

        df = pd.DataFrame(rows)
        df = normalize_frame(
            df,
            categorical=cat_cols,
            numerical=num_cols,
        )

        X = df[ordered]

        cost_ape = self.cost_model.predict(X)
        runtime_ape = self.runtime_model.predict(X)

        return [
            {
                "predicted_cost_ape": max(0.0, float(c)),
                "predicted_runtime_ape": max(0.0, float(r)),
            }
            for c, r in zip(cost_ape, runtime_ape)
        ]
