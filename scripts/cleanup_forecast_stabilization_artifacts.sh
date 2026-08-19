#!/usr/bin/env bash
set -euo pipefail
targets=(apply.sh apply-combined.sh apply-incremental.sh apply-current-main.sh cleanup_generated_artifacts.sh budget-constrained-router.md)
git rm -f --ignore-unmatch -- "${targets[@]}" || true
git rm -f --ignore-unmatch -- .DS_Store || true
