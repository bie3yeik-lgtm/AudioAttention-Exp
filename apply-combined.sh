#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
git apply --check "$here/AudioAttention-Exp-forecast-aware-budget-pacing.patch"
git apply "$here/AudioAttention-Exp-forecast-aware-budget-pacing.patch"
python -m pytest -q tests/test_budget_ledger.py tests/test_workflow_paths.py
