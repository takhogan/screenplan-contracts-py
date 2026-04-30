#!/usr/bin/env bash
# Clean → codegen → install in editable mode → run tests.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

bash scripts/clean.sh
bash scripts/codegen.sh
pip install --quiet -e .
python -m pytest -q
echo "[build] done"
