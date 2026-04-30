#!/usr/bin/env bash
# Refresh screenplan-contracts-schemas from github, regenerate models,
# install + test, then commit + push any changes.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

pip install --quiet --force-reinstall --no-deps \
  "screenplan-contracts-schemas @ git+https://github.com/takhogan/screenplan-contracts.git@main"
bash scripts/build.sh  # clean → codegen → install -e . → pytest

git add -A
if git diff --cached --quiet; then
  echo "[py] no changes to commit"
else
  git commit -m "make deploy commit $(date '+%Y-%m-%d %H:%M:%S')"
fi
git push origin main
