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



def _env_bool(name: str | None, default: bool) -> bool:
    if not name:
        return default
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean for {name}: {raw}")


def resolved_pacing(cfg: dict[str, Any]) -> dict[str, Any]:
    source = cfg.get("pacing", {})
    envs = source.get("env_overrides", {})

    mode = os.environ.get(envs.get("mode", ""), source.get("mode", "enforce"))
    if mode not in {"enforce", "advisory"}:
        raise ValueError(f"Unsupported pacing mode: {mode}")

    return {
        "enabled": _env_bool(envs.get("enabled"), bool(source.get("enabled", True))),
        "mode": mode,
        "pace_multiplier": _env_float(
            envs.get("pace_multiplier"), float(source.get("pace_multiplier", 1.0))
        ),
        "min_daily_allowance_usd": _env_float(
            envs.get("min_daily_allowance_usd"),
            float(source.get("min_daily_allowance_usd", 0.0)),
        ),
        "max_daily_allowance_usd": _env_float(
            envs.get("max_daily_allowance_usd"), source.get("max_daily_allowance_usd")
        ),
    }
