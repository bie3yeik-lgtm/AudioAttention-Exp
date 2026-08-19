#!/usr/bin/env bash
set -euo pipefail

git rm -r --ignore-unmatch infra/infra
git rm --ignore-unmatch .DS_Store infra/.DS_Store

echo "Removed duplicated infra/infra and tracked .DS_Store files when present."
