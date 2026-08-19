#!/usr/bin/env python3
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]

def patch_budgeted():
    p=ROOT/".github/workflows/budgeted-unified-job.yml"
    t=p.read_text()

    keys={
        "GPU_BUDGET_PACING_ENABLED",
        "GPU_BUDGET_PACING_MODE",
        "GPU_BUDGET_PACING_MULTIPLIER",
        "GPU_BUDGET_PACING_MIN_DAILY_USD",
        "GPU_BUDGET_PACING_MAX_DAILY_USD",
    }
    seen=set()
    out=[]
    pat=re.compile(r"^(\s+)(GPU_BUDGET_PACING_[A-Z0-9_]+):")
    for line in t.splitlines():
        m=pat.match(line)
        if m and m.group(2) in keys:
            if m.group(2) in seen:
                continue
            seen.add(m.group(2))
        out.append(line)
    t="\n".join(out)+("\n" if t.endswith("\n") else "")

    failure='      GPU_BUDGET_FORECAST_ACTIONS_FAILURE_MODE: ${{ vars.GPU_BUDGET_FORECAST_ACTIONS_FAILURE_MODE }}'
    anchor='      GPU_BUDGET_FORECAST_SCHEDULE_WEIGHT: ${{ vars.GPU_BUDGET_FORECAST_SCHEDULE_WEIGHT }}'
    if failure not in t:
        if anchor not in t:
            raise RuntimeError("budgeted workflow: forecast schedule-weight anchor not found")
        t=t.replace(anchor,anchor+"\n"+failure,1)

    if "auto_forecast_stabilized.py" not in t:
        old="python infra/budget_ledger/auto_forecast.py"
        if old not in t:
            raise RuntimeError("budgeted workflow: auto_forecast.py call not found")
        t=t.replace(old,"python infra/budget_ledger/auto_forecast_stabilized.py",1)

    p.write_text(t)

def patch_report():
    p=ROOT/".github/workflows/budget-forecast-report.yml"
    t=p.read_text()

    failure='      GPU_BUDGET_FORECAST_ACTIONS_FAILURE_MODE: ${{ vars.GPU_BUDGET_FORECAST_ACTIONS_FAILURE_MODE }}'
    anchor='      GPU_BUDGET_FORECAST_SCHEDULE_WEIGHT: ${{ vars.GPU_BUDGET_FORECAST_SCHEDULE_WEIGHT }}'
    if failure not in t:
        if anchor not in t:
            raise RuntimeError("report workflow: forecast schedule-weight anchor not found")
        t=t.replace(anchor,anchor+"\n"+failure,1)

    if "auto_forecast_stabilized.py" not in t:
        old="python infra/budget_ledger/auto_forecast.py"
        if old not in t:
            raise RuntimeError("report workflow: auto_forecast.py call not found")
        t=t.replace(old,"python infra/budget_ledger/auto_forecast_stabilized.py",1)

    collapsed='          python infra/budget_ledger/forecast_report.py             --bucket "$HF_BUCKET"             --workload \'${{ matrix.workload }}\'             | tee forecast.json'
    if collapsed in t:
        multiline=(
            '          python infra/budget_ledger/forecast_report.py \\\n'
            '            --bucket "$HF_BUCKET" \\\n'
            "            --workload '${{ matrix.workload }}' \\\n"
            '            | tee forecast.json'
        )
        t=t.replace(collapsed,multiline,1)

    p.write_text(t)

def patch_sources():
    p=ROOT/"configs/forecast-sources.yaml"
    t=p.read_text()
    if re.search(r"(?m)^\s*failure_mode:\s*(degraded|fail_closed)\s*$",t):
        return
    anchor='  budgeted_run_name_prefix: "budgeted|"'
    if anchor not in t:
        raise RuntimeError("forecast-sources: budgeted_run_name_prefix not found")
    ins=(
        anchor
        + "\n  # degraded: continue with partial demand and lower forecast health."
        + "\n  # fail_closed: abort if any Actions query fails."
        + "\n  failure_mode: degraded"
    )
    p.write_text(t.replace(anchor,ins,1))

def main():
    patch_budgeted()
    patch_report()
    patch_sources()
    print("Forecast Stabilization v6 update complete.")

if __name__=="__main__":
    main()
