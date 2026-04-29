"""Pydantic v2 models mirroring packages/screenplan-contracts/schemas/*.

The JSON schemas are the source of truth; these models exist for ergonomic
Python-side use. Keep field names identical to the schemas.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field

# ---------- enums ----------

SystemName = Literal["python", "adb", "kvm", "none"]
RunStatus = Literal["RUNNING", "SUCCESS", "FAILURE", "ERROR"]
FileType = Literal["text", "image", "video", "directory"]
ScriptMode = Literal["train", "test", "prod"]
EditorStatus = Literal["dirty", "clean", "error"]
ArtifactPresence = Literal["always", "optional", "never"]

SCRIPT_ACTION_NAMES = (
    "jointAction",
    "clickAction",
    "mouseScrollAction",
    "declareScene",
    "conditionalStatement",
    "shellScript",
    "logAction",
    "sleepStatement",
    "variableAssignment",
    "timeAction",
    "randomVariable",
    "scriptReference",
    "dragLocationSource",
    "dragLocationTarget",
    "detectObject",
    "keyboardAction",
    "searchPatternStartAction",
    "searchPatternContinueAction",
    "searchPatternEndAction",
    "randomizerAction",
    "jsonFileAction",
    "exceptionAction",
    "navigateAction",
    "ImageToTextAction",
    "scale",
    "sendMessageAction",
    "codeBlock",
    "forLoopAction",
    "ADBConfigurationAction",
    "colorCompareAction",
    "returnStatement",
    "imageTransformationAction",
    "countToThresholdAction",
    "fileIOAction",
    "maskMergeAction",
    "mouseMoveAction",
    "mouseInteractionAction",
    "userPromptAction",
    "calendarAction",
    "userSecretManagementAction",
    "interactApplicationAction",
)


class _Loose(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# ---------- ScriptAction / Script ----------

class ScriptActionData(_Loose):
    targetSystem: SystemName


class ScriptAction(_Loose):
    actionName: str
    actionData: ScriptActionData
    actionGroup: int
    actionVersion: int
    actionVersionCode: str
    actionLabel: str
    actionRowRowIndex: int
    actionRowActionIndex: int
    visualizerRowIndex: int
    visualizerActionIndex: int
    visualizerX: float
    visualizerY: float
    childGroups: List[Dict[str, Any]]
    parentGroups: List[int]
    displayables: List[Dict[str, Any]]
    configurables: List[Dict[str, Any]]
    linkingBehaviors: List[Dict[str, Any]]
    actionIcon: Any = None
    actionGroups: Optional[List[int]] = None
    selected: Optional[bool] = None
    draggable: Optional[bool] = None
    highlight: Optional[str] = None
    helpTipExpanded: Optional[bool] = None


class ScriptActionRow(_Strict):
    actions: List[ScriptAction]
    actionRowIndex: int
    rowID: int
    selected: bool


class ScriptProps(_Loose):
    targetSystem: SystemName
    width: float
    height: float
    scriptMode: ScriptMode
    deploymentToLibrary: bool
    scriptReference: Optional[Dict[str, Any]] = None


class ScriptMeta(_Strict):
    editorStatus: EditorStatus


class Script(_Strict):
    scriptName: str
    actionRows: List[ScriptActionRow]
    props: ScriptProps
    dependencies: List[str]
    inputs: List[Tuple[str, str, bool]]
    outputs: List[Tuple[str, str, bool]]
    scriptMeta: ScriptMeta
    id: str
    interfaceVersion: int
    lastLoadedTimestamp: Optional[float] = None


# ---------- ScriptStatus / EventStatus ----------

class ScriptStatus(_Loose):
    script_id: str
    script_name: str
    status: str
    script_duration: str
    log_level: str
    notification_level: str
    system_script: bool
    args: List[Any]
    parallel: bool
    start_time_str: Optional[str] = None
    end_time_str: Optional[str] = None
    device_details: Optional[Dict[str, Any]] = None
    script_log_folder: Optional[str] = None
    showDetails: Optional[bool] = None


class _SeqCommand(_Loose):
    type: Literal["command"]
    key: str
    value: Union[str, int, float, bool, None]
    status: str


class _SeqVariable(_Loose):
    type: Literal["variable"]
    key: str
    value: Any
    status: str


class _SeqScript(_Loose):
    type: Literal["script"]
    script_name: str
    status: str


class _SeqNested(_Loose):
    type: Literal["sequence"]
    sequence_name: str
    sequence: List["EventSequenceItem"]
    status: str
    sequences: Optional[Dict[str, Any]] = None


EventSequenceItem = Union[_SeqCommand, _SeqVariable, _SeqScript, _SeqNested]
_SeqNested.model_rebuild()


class EventStatus(_Loose):
    event_id: str
    type: Literal["sequence"]
    sequence_name: str
    status: str
    sequence: List[EventSequenceItem]
    start_time: Optional[str] = None
    timeout: Optional[str] = None
    end_time_str: Optional[str] = None
    sequences: Optional[Dict[str, Any]] = None


# ---------- ScriptActionLog ----------

class ScriptActionLogFile(_Strict):
    file_type: FileType
    file_path: str


class ScriptActionLogChildStub(_Strict):
    id: str
    script_counter: int
    log_object_type: Literal["action", "script"]
    tree_entity_type: Literal["child"]
    action_log_path: str


def _coerce_file(value: Any) -> Optional[ScriptActionLogFile]:
    """ScriptActionLog file slots are serialised as `{}` when no file is attached."""
    if value is None or value == {} or value == "":
        return None
    if isinstance(value, ScriptActionLogFile):
        return value
    return ScriptActionLogFile.model_validate(value)


class ScriptActionLog(_Loose):
    base_path: str
    action_log_path: str
    id: str
    name: str
    target_system: SystemName
    script_log_folder: Optional[str]
    script_counter: int
    log_object_type: Literal["action", "script"]
    tree_entity_type: Literal["node", "child"]
    status: RunStatus
    summary: str
    start_time: str
    elapsed: float
    async_elapsed: float
    pre_file: Optional[ScriptActionLogFile] = None
    post_file: Optional[ScriptActionLogFile] = None
    supporting_files: List[ScriptActionLogFile] = Field(default_factory=list)
    children: List[ScriptActionLogChildStub] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    script_name: Optional[str] = None

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):  # type: ignore[override]
        if isinstance(obj, dict):
            obj = dict(obj)
            if "pre_file" in obj:
                obj["pre_file"] = _coerce_file(obj["pre_file"])
            if "post_file" in obj:
                obj["post_file"] = _coerce_file(obj["post_file"])
        return super().model_validate(obj, *args, **kwargs)


# ---------- artifacts spec ----------

class ArtifactFileSlot(_Strict):
    file_type: FileType
    presence: ArtifactPresence
    name_suffix: Optional[str] = None
    description: Optional[str] = None


class ArtifactAttributeSpec(_Strict):
    presence: Literal["always", "optional"]
    enum: Optional[List[str]] = None
    description: Optional[str] = None


class ActionArtifactSpec(_Strict):
    pre_file: ArtifactFileSlot
    post_file: ArtifactFileSlot
    supporting_files: List[ArtifactFileSlot]
    attributes: Optional[Dict[str, ArtifactAttributeSpec]] = None


class ScriptActionArtifactsSpec(_Loose):
    version: int
    actions: Dict[str, ActionArtifactSpec]
