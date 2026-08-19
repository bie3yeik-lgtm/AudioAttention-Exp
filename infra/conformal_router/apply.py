from __future__ import annotations

from typing import Any

from model import ConformalCalibration


def apply_conformal(
    candidates: list[dict[str, Any]],
    *,
    bucket: str,
    workload: str,
    config_path: str = "configs/conformal-router.yaml",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        cal = ConformalCalibration.load_latest(
            bucket,
            config_path=config_path,
        )

        out = []

        for candidate in candidates:
            predicted_cost = float(
                candidate.get(
                    "contextual_blended_total_cost_usd",
                    candidate.get(
                        "risk_adjusted_total_cost_usd",
                        candidate.get(
                            "predicted_total_cost_usd",
                            0.0,
                        ),
                    ),
                )
            )

            predicted_runtime = float(
                candidate.get(
                    "predicted_runtime_seconds",
                    float(
                        candidate.get(
                            "predicted_runtime_hours",
                            0.0,
                        )
                    )
                    * 3600.0,
                )
            )

            gpu_id = str(
                candidate.get("gpu_id")
                or candidate.get("flavor")
                or "unknown"
            )

            bounds = cal.bounds(
                workload=workload,
                provider=candidate["provider"],
                gpu_id=gpu_id,
                predicted_cost_usd=predicted_cost,
                predicted_runtime_seconds=predicted_runtime,
            )

            c = dict(candidate)
            c["conformal"] = bounds

            # For cost-minimizing exploration, lower bound is optimistic.
            c["conformal_lcb_cost_usd"] = bounds["cost_lower_usd"]
            c["conformal_ucb_cost_usd"] = bounds["cost_upper_usd"]

            out.append(c)

        return out, {
            "source": "conformal",
            "coverage_target": cal.payload["coverage"],
            "created_at": cal.payload["created_at"],
        }

    except Exception as exc:
        return candidates, {
            "source": "unavailable",
            "error": repr(exc),
        }
