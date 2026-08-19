#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"

git apply --check "$here/AudioAttention-Exp-forecast-stabilization-v7.patch"
git apply "$here/AudioAttention-Exp-forecast-stabilization-v7.patch"

python scripts/apply_forecast_stabilization_v7.py
bash scripts/cleanup_forecast_stabilization_artifacts.sh

python -m pytest -q tests/test_forecast_stabilization_v7.py
