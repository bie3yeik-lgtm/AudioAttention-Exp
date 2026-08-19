from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

# Import source gate by path in callers or ensure PYTHONPATH contains
# infra/contextual_router.
from source_gate import prediction_source


def call_contextual(
    *,
    workload: str,
    units: float,
    job_spec: str,
    bucket: str,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        "infra/contextual_router:infra/historical_router:"
        + env.get("PYTHONPATH", "")
    )

    p = subprocess.run(
        [
            sys.executable,
            "infra/contextual_router/select_contextual.py",
            "--workload",
            workload,
            "--units",
            str(units),
            "--job-spec",
            job_spec,
            "--bucket",
            bucket,
            "--mode",
            "advisory",
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip())

    return json.loads(p.stdout)


def choose_prediction_candidates(
    *,
    workload: str,
    bucket: str,
    historical_result: dict[str, Any],
    units: float,
    job_spec: str | None,
    requested_source: str = "auto",
) -> tuple[list[dict[str, Any]], str, dict[str, Any] | None]:
    source, report, _ = prediction_source(
        bucket,
        workload,
        requested=requested_source,
    )

    if source != "contextual" or not job_spec:
        return historical_result["candidates"], "historical", report

    contextual = call_contextual(
        workload=workload,
        units=units,
        job_spec=job_spec,
        bucket=bucket,
    )

    candidates = []
    for c in contextual["candidates"]:
        # Normalize Contextual prediction into the fields Bandit expects.
        c = dict(c)
        c["risk_adjusted_total_cost_usd"] = float(
            c["contextual_blended_total_cost_usd"]
        )
        c["predicted_total_cost_usd"] = float(
            c["contextual_blended_total_cost_usd"]
        )
        c["prediction_source"] = "contextual"
        candidates.append(c)

    return candidates, "contextual", report
