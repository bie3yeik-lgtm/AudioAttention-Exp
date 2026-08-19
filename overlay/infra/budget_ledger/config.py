from __future__ import annotations

import os
from typing import Any

import yaml


def load_config(path: str = "configs/budget-ledger.yaml") -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _env_float(name: str | None, default: float | None) -> float | None:
    if not name:
        return default
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return float(raw)


def resolved_limits(cfg: dict[str, Any]) -> dict[str, dict[str, float | None]]:
    limits = cfg["limits"]
    envs = cfg.get("env_overrides", {})
    out: dict[str, dict[str, float | None]] = {}

    def resolve(source: dict[str, Any], env_source: dict[str, Any]) -> dict[str, float | None]:
        return {
            "daily": _env_float(env_source.get("daily_usd"), source.get("daily_usd")),
            "weekly": _env_float(env_source.get("weekly_usd"), source.get("weekly_usd")),
            "monthly": _env_float(env_source.get("monthly_usd"), source.get("monthly_usd")),
        }

    out["global"] = resolve(limits.get("global", {}), envs.get("global", {}))
    for workload, wl_limits in limits.get("workloads", {}).items():
        out[f"workload:{workload}"] = resolve(
            wl_limits,
            envs.get("workloads", {}).get(workload, {}),
        )
    return out
