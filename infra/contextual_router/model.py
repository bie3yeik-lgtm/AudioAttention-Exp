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


class ContextualModel:
    def __init__(
        self,
        runtime_model: CatBoostRegressor,
        cost_model: CatBoostRegressor,
        metadata: dict[str, Any],
    ) -> None:
        self.runtime_model = runtime_model
        self.cost_model = cost_model
        self.metadata = metadata

    @classmethod
    def load_latest(
        cls,
        bucket: str,
        *,
        config_path: str = "configs/contextual-router.yaml",
    ) -> "ContextualModel":
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
            runtime_path = td / "runtime.cbm"
            cost_path = td / "cost.cbm"

            for remote_name, local in [
                (rcfg["runtime_model_file"], runtime_path),
                (rcfg["cost_model_file"], cost_path),
            ]:
                remote = f"hf://buckets/{bucket}/{prefix}/{remote_name}"
                with fs.open(remote, "rb") as src, local.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

            runtime_model = CatBoostRegressor()
            runtime_model.load_model(str(runtime_path))

            cost_model = CatBoostRegressor()
            cost_model.load_model(str(cost_path))

        return cls(
            runtime_model=runtime_model,
            cost_model=cost_model,
            metadata=latest["metadata"],
        )

    def predict(self, rows: list[dict[str, Any]]) -> list[dict[str, float]]:
        feature_cfg = self.metadata["features"]
        categorical = feature_cfg["categorical"]
        numerical = feature_cfg["numerical"]
        ordered = feature_cfg["ordered"]

        df = pd.DataFrame(rows)
        df = normalize_frame(
            df,
            categorical=categorical,
            numerical=numerical,
        )

        X = df[ordered]

        runtime = self.runtime_model.predict(X)
        cost = self.cost_model.predict(X)

        return [
            {
                "predicted_runtime_seconds": max(0.0, float(r)),
                "predicted_total_cost_usd": max(0.0, float(c)),
            }
            for r, c in zip(runtime, cost)
        ]
