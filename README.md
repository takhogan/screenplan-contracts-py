# screenplan-contracts (Python)

Shared Pydantic models, JSON schemas, and validation helpers for ScreenPlan (Script, ScriptAction, ScriptActionLog, queue entries). Schemas come from [`screenplan-contracts`](https://github.com/takhogan/screenplan-contracts).

## Install

```bash
pip install -e packages/screenplan-contracts-py
```

Requires Python ≥ 3.9.

## Usage

```python
from screenplan_contracts.models import Script
from screenplan_contracts.validation import validate_script

script = Script.model_validate(payload)
validate_script(payload)  # raises jsonschema.ValidationError on failure
```

Modules:
- `models.py` — Pydantic v2 models.
- `validation.py` — `jsonschema`-based validators against the upstream schemas.

## Tests

```bash
python -m pytest packages/screenplan-contracts-py/tests
```
