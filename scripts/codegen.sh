#!/usr/bin/env bash
# Regenerate Pydantic models from the canonical JSON schemas in
# screenplan-contracts-schemas. The generated tree lives at
# screenplan_contracts/_generated and is re-exported (with semantic shims)
# by screenplan_contracts/models.py.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
# CONTRACTS_DIR: another checkout of screenplan-contracts, such as a worktree.
CONTRACTS_DIR="${CONTRACTS_DIR:-$HERE/../screenplan-contracts}"
SCHEMAS="$(cd "$CONTRACTS_DIR/screenplan_contracts_schemas/schemas" && pwd)"
OUT="$HERE/screenplan_contracts/_generated"

rm -rf "$OUT"
python -m datamodel_code_generator \
  --input "$SCHEMAS" \
  --input-file-type jsonschema \
  --output "$OUT" \
  --output-model-type pydantic_v2.BaseModel \
  --target-python-version 3.10 \
  --use-schema-description \
  --snake-case-field \
  --use-double-quotes \
  --use-annotated \
  --use-subclass-enum \
  --reuse-model
echo "[codegen] wrote $OUT"
