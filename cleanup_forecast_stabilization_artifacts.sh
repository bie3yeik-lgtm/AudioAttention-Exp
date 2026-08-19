#!/usr/bin/env bash
set -euo pipefail
targets=(apply.sh apply-combined.sh apply-incremental.sh apply-current-main.sh cleanup_generated_artifacts.sh budget-constrained-router.md .DS_Store)
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git rm -f --ignore-unmatch -- "${targets[@]}"
else
  rm -f -- "${targets[@]}"
fi
