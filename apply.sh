#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
patch="$here/AudioAttention-Exp-cleanup-auto-demand-forecast.patch"

git apply --check "$patch"
git apply "$patch"
python "$here/upgrade_auto_forecast.py"
bash "$here/cleanup_generated_artifacts.sh"
python -m pytest -q tests/test_budget_ledger.py tests/test_auto_forecast.py
