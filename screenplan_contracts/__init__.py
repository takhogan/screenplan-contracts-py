"""ScreenPlan shared Pydantic models, JSON schemas and validation helpers.

Public package: ``screenplan-contracts`` (PyPI), import as ``screenplan_contracts``.
"""

from .models import (
    ArtifactAttributeSpec,
    ArtifactFileSlot,
    ActionArtifactSpec,
    EventSequenceItem,
    EventStatus,
    Script,
    ScriptAction,
    ScriptActionArtifactsSpec,
    ScriptActionLog,
    ScriptActionLogChildStub,
    ScriptStatus,
    SystemName,
    RunStatus,
)
from screenplan_contracts_schemas import list_schemas
from .validation import (
    ContractValidationError,
    get_artifacts_spec,
    load_schema,
    validate_event_status,
    validate_script,
    validate_script_action,
    validate_script_action_log,
    validate_script_status,
)

__all__ = [
    "ArtifactAttributeSpec",
    "ArtifactFileSlot",
    "ActionArtifactSpec",
    "ContractValidationError",
    "EventSequenceItem",
    "EventStatus",
    "RunStatus",
    "Script",
    "ScriptAction",
    "ScriptActionArtifactsSpec",
    "ScriptActionLog",
    "ScriptActionLogChildStub",
    "ScriptStatus",
    "SystemName",
    "get_artifacts_spec",
    "list_schemas",
    "load_schema",
    "validate_event_status",
    "validate_script",
    "validate_script_action",
    "validate_script_action_log",
    "validate_script_status",
]
