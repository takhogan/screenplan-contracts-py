"""Public Pydantic models for screenplan-contracts.

The classes are generated from the JSON schemas in screenplan-contracts-schemas
via ``datamodel-code-generator`` (see ``scripts/codegen.sh``). This module is a
thin shim that re-exports the generated classes under stable public names and
adds the few semantic behaviours that the schema cannot express (currently:
coercing ``{}`` FilePair to ``None`` on ScriptActionLog).
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import field_validator

from ._generated.common_schema import (
    FilePair,
    FilePair1 as FilePairItem,
    FileType,
    QueueStatus,
    RunStatus,
    SystemName,
)
from ._generated.event_status_schema import (
    EventStatus,
    SequenceItem as EventSequenceItem,
    NestedSequenceItem,
    CommandItem,
    VariableItem,
    ScriptItem,
)
from ._generated.script_schema import (
    Script,
    ScriptActionRow,
    ScriptMeta,
    ScriptProps,
)
from ._generated.script_action_schema import (
    ActionName,
    ScriptAction,
)
from ._generated.script_action_data_schema import (
    ScriptActionData,
)
from ._generated.script_action_log_schema import (
    ChildStub as ScriptActionLogChildStub,
    LogObjectType,
    ScriptActionLog as _GeneratedScriptActionLog,
    TreeEntityType,
)
from ._generated.script_action_artifacts_schema import (
    ActionArtifactSpec,
    Attributes as ArtifactAttributeSpec,
    FileSlot as ArtifactFileSlot,
    ScriptActionArtifactsSpec,
)


def _coerce_empty_filepair(value: Any) -> Any:
    if isinstance(value, dict) and not value:
        return None
    if isinstance(value, list):
        return [_coerce_empty_filepair(v) for v in value]
    return value


class ScriptActionLog(_GeneratedScriptActionLog):
    """ScriptActionLog with `{}` FilePair coerced to `None` for ergonomic access."""

    pre_file: Optional[FilePair] = None
    post_file: Optional[FilePair] = None
    supporting_files: list[Optional[FilePair]] = []  # type: ignore[assignment]

    @field_validator("pre_file", "post_file", "supporting_files", mode="before")
    @classmethod
    def _empty_to_none(cls, v: Any) -> Any:
        return _coerce_empty_filepair(v)


__all__ = [
    "ActionArtifactSpec",
    "ActionName",
    "ArtifactAttributeSpec",
    "ArtifactFileSlot",
    "CommandItem",
    "EventSequenceItem",
    "EventStatus",
    "FilePair",
    "FilePairItem",
    "FileType",
    "LogObjectType",
    "NestedSequenceItem",
    "QueueStatus",
    "RunStatus",
    "Script",
    "ScriptAction",
    "ScriptActionArtifactsSpec",
    "ScriptActionData",
    "ScriptActionLog",
    "ScriptActionLogChildStub",
    "ScriptActionRow",
    "ScriptItem",
    "ScriptMeta",
    "ScriptProps",
    "SystemName",
    "TreeEntityType",
    "VariableItem",
]


# Backwards-compat alias kept here for ScriptStatus, which the generator places
# in script_status_schema. We import lazily in case codegen ordering changes.
from ._generated.script_status_schema import ScriptStatus  # noqa: E402

__all__.append("ScriptStatus")
