#!/usr/bin/env bash
# Remove generated artifacts (Pydantic models + caches).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

rm -rf screenplan_contracts/_generated
find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
find . -type d -name '*.egg-info' -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache build dist
echo "[clean] done"
