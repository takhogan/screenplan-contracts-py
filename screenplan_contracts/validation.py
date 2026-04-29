"""JSON-schema and Pydantic validation helpers for ScreenPlan contracts.

Schema files are shipped by the sibling ``screenplan-contracts-schemas``
package and loaded via ``importlib.resources`` so PyInstaller-frozen builds
work.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict

from jsonschema import Draft202012Validator, RefResolver
from screenplan_contracts_schemas import schema_text as _schema_text

from . import models as _models


class ContractValidationError(ValueError):
    """Raised when a JSON document fails its ScreenPlan contract schema."""

    def __init__(self, contract: str, errors: Any) -> None:
        super().__init__(f"screenplan-contracts: {contract} validation failed: {errors}")
        self.contract = contract
        self.errors = errors


@lru_cache(maxsize=None)
def load_schema(name: str) -> Dict[str, Any]:
    """Load a packaged JSON schema (or example/data JSON) by filename."""
    return json.loads(_schema_text(name))


@lru_cache(maxsize=1)
def _store() -> Dict[str, Dict[str, Any]]:
    """Build the schema store keyed by filename so cross-file $ref works."""
    names = [
        "common.schema.json",
        "script-action.schema.json",
        "script.schema.json",
        "script-status.schema.json",
        "event-status.schema.json",
        "script-action-log.schema.json",
        "script-action-artifacts.schema.json",
    ]
    return {name: load_schema(name) for name in names}


def _validator(schema_name: str) -> Draft202012Validator:
    schema = load_schema(schema_name)
    resolver = RefResolver.from_schema(
        schema,
        store={f"https://screenplan.local/schemas/{n}": s for n, s in _store().items()}
        | {n: s for n, s in _store().items()},
    )
    return Draft202012Validator(schema, resolver=resolver)


def _run(schema_name: str, contract: str, data: Any) -> None:
    errors = sorted(_validator(schema_name).iter_errors(data), key=lambda e: e.path)
    if errors:
        raise ContractValidationError(
            contract,
            [{"path": list(e.path), "message": e.message} for e in errors],
        )


# ---- public API: schema-level validation ------------------------------------

def validate_script(data: Any) -> _models.Script:
    _run("script.schema.json", "Script", data)
    return _models.Script.model_validate(data)


def validate_script_action(data: Any) -> _models.ScriptAction:
    _run("script-action.schema.json", "ScriptAction", data)
    return _models.ScriptAction.model_validate(data)


def validate_script_status(data: Any) -> _models.ScriptStatus:
    _run("script-status.schema.json", "ScriptStatus", data)
    return _models.ScriptStatus.model_validate(data)


def validate_event_status(data: Any) -> _models.EventStatus:
    _run("event-status.schema.json", "EventStatus", data)
    return _models.EventStatus.model_validate(data)


def validate_script_action_log(data: Any) -> _models.ScriptActionLog:
    _run("script-action-log.schema.json", "ScriptActionLog", data)
    return _models.ScriptActionLog.model_validate(data)


def validate_artifacts_spec(data: Any) -> _models.ScriptActionArtifactsSpec:
    _run("script-action-artifacts.schema.json", "ScriptActionArtifactsSpec", data)
    return _models.ScriptActionArtifactsSpec.model_validate(data)


@lru_cache(maxsize=1)
def get_artifacts_spec() -> _models.ScriptActionArtifactsSpec:
    """Load and validate the canonical per-action artifacts spec."""
    return validate_artifacts_spec(load_schema("script-action-artifacts.json"))
