#!/usr/bin/env python3
from pathlib import Path


def patch_budgeted():
    p = Path('.github/workflows/budgeted-unified-job.yml')
    t = p.read_text(encoding='utf-8')

    if 'run-name: "budgeted|' not in t:
        t = t.replace(
            'name: Budgeted Unified GPU Job\n',
            'name: Budgeted Unified GPU Job\nrun-name: "budgeted|${{ inputs.job_spec_path }}|${{ inputs.units }}"\n',
            1,
        )

    if '  actions: read\n' not in t:
        t = t.replace(
            'permissions:\n  contents: read\n',
            'permissions:\n  contents: read\n  actions: read\n',
            1,
        )

    anchor = '      GPU_BUDGET_STUDENT_MONTHLY_USD: ${{ vars.GPU_BUDGET_STUDENT_MONTHLY_USD }}\n'
    block = (
        '      GPU_BUDGET_PACING_ENABLED: ${{ vars.GPU_BUDGET_PACING_ENABLED }}\n'
        '      GPU_BUDGET_PACING_MODE: ${{ vars.GPU_BUDGET_PACING_MODE }}\n'
        '      GPU_BUDGET_PACING_MULTIPLIER: ${{ vars.GPU_BUDGET_PACING_MULTIPLIER }}\n'
        '      GPU_BUDGET_PACING_MIN_DAILY_USD: ${{ vars.GPU_BUDGET_PACING_MIN_DAILY_USD }}\n'
        '      GPU_BUDGET_PACING_MAX_DAILY_USD: ${{ vars.GPU_BUDGET_PACING_MAX_DAILY_USD }}\n'
        '      GPU_BUDGET_FORECAST_ENABLED: ${{ vars.GPU_BUDGET_FORECAST_ENABLED }}\n'
        '      GPU_BUDGET_FORECAST_LOOKBACK_DAYS: ${{ vars.GPU_BUDGET_FORECAST_LOOKBACK_DAYS }}\n'
        '      GPU_BUDGET_FORECAST_BASELINE_WEIGHT: ${{ vars.GPU_BUDGET_FORECAST_BASELINE_WEIGHT }}\n'
        '      GPU_BUDGET_FORECAST_WEEKDAY_WEIGHT: ${{ vars.GPU_BUDGET_FORECAST_WEEKDAY_WEIGHT }}\n'
        '      GPU_BUDGET_FORECAST_SCHEDULE_WEIGHT: ${{ vars.GPU_BUDGET_FORECAST_SCHEDULE_WEIGHT }}\n'
    )
    if 'GPU_BUDGET_FORECAST_LOOKBACK_DAYS' not in t:
        if anchor not in t:
            raise RuntimeError('reserve env anchor not found')
        t = t.replace(anchor, anchor + block, 1)

    auto_step = (
        '      - name: Build automatic demand forecast\n'
        '        env:\n'
        '          PYTHONPATH: infra/budget_ledger\n'
        '          GITHUB_TOKEN: ${{ github.token }}\n'
        '          GITHUB_REPOSITORY: ${{ github.repository }}\n'
        '        run: |\n'
        '          forecast_file="$RUNNER_TEMP/budget-demand-forecast.generated.yaml"\n'
        '          python infra/budget_ledger/auto_forecast.py \\\n'
        '            --bucket "$HF_BUCKET" \\\n'
        "            --exclude-run-id '${{ github.run_id }}' \\\n"
        '            --output "$forecast_file"\n'
        '          echo "GPU_BUDGET_FORECAST_FILE=$forecast_file" >> "$GITHUB_ENV"\n'
        '\n'
    )
    if 'Build automatic demand forecast' not in t:
        marker = '      - name: Reserve shared budget\n'
        if marker in t:
            t = t.replace(marker, auto_step + marker, 1)
        else:
            compact = (
                '      - env:\n'
                '          PYTHONPATH: infra/budget_ledger\n'
                '        run: |\n'
                '          python infra/budget_ledger/reserve.py'
            )
            if compact not in t:
                raise RuntimeError('reserve step anchor not found')
            t = t.replace(compact, auto_step + compact, 1)

    p.write_text(t, encoding='utf-8')


def patch_report():
    p = Path('.github/workflows/budget-forecast-report.yml')
    if not p.exists():
        return
    t = p.read_text(encoding='utf-8')
    if '  actions: read\n' not in t:
        t = t.replace(
            'permissions:\n  contents: read\n',
            'permissions:\n  contents: read\n  actions: read\n',
            1,
        )
    if 'Build automatic demand forecast' not in t:
        marker = '      - name: Forecast-aware pacing report\n'
        step = (
            '      - name: Build automatic demand forecast\n'
            '        env:\n'
            '          PYTHONPATH: infra/budget_ledger\n'
            '          GITHUB_TOKEN: ${{ github.token }}\n'
            '          GITHUB_REPOSITORY: ${{ github.repository }}\n'
            '        run: |\n'
            '          forecast_file="$RUNNER_TEMP/budget-demand-forecast.generated.yaml"\n'
            '          python infra/budget_ledger/auto_forecast.py \\\n'
            '            --bucket "$HF_BUCKET" \\\n'
            "            --exclude-run-id '${{ github.run_id }}' \\\n"
            '            --output "$forecast_file"\n'
            '          echo "GPU_BUDGET_FORECAST_FILE=$forecast_file" >> "$GITHUB_ENV"\n'
            '\n'
        )
        if marker not in t:
            raise RuntimeError('forecast report anchor not found')
        t = t.replace(marker, step + marker, 1)
    p.write_text(t, encoding='utf-8')


if __name__ == '__main__':
    patch_budgeted()
    patch_report()
