#!/usr/bin/env bash
set -euo pipefail
BASE_SHA="8c20441198dd6890da4d1d28393083b3ec11d260"
HERE="$(cd "$(dirname "$0")" && pwd)"
CURRENT="$(git rev-parse HEAD)"
if [ "$CURRENT" != "$BASE_SHA" ]; then
  echo "warning: inspected base was $BASE_SHA but current HEAD is $CURRENT" >&2
  echo "running git apply --check; review conflicts if it fails" >&2
fi
git apply --check "$HERE/AudioAttention-Exp-budget-ledger.patch"
git apply "$HERE/AudioAttention-Exp-budget-ledger.patch"
bash scripts/stabilize_repository.sh
echo "Patch applied. Review with: git status && git diff"
