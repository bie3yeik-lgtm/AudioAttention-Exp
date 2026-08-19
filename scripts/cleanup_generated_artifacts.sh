#!/usr/bin/env bash
set -euo pipefail
root_artifacts=(
  .DS_Store APPLY.md PATCH_NOTES.md FULL_CLOUD_SOURCE.md
  AudioAttention-Exp-budget-ledger.patch
  AudioAttention-Exp-job-kind-budget-pacing.patch
  AudioAttention-Exp-forecast-aware-budget-pacing.patch
  AudioAttention-Exp-forecast-aware-budget-pacing-incremental.patch
)
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git rm -f --ignore-unmatch -- "${root_artifacts[@]}" || true
  while IFS= read -r -d '' p; do
    git rm -f --ignore-unmatch -- "$p" >/dev/null 2>&1 || rm -f -- "$p"
  done < <(find . -name .DS_Store -print0)
else
  rm -f -- "${root_artifacts[@]}"
  find . -name .DS_Store -delete
fi
