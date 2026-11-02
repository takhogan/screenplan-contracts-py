"""Smoke tests for shared_contracts: validate every example JSON."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from screenplan_contracts import (
    ContractValidationError,
    get_artifacts_spec,
    validate_event_status,
    validate_script_action_log,
    validate_agent_tool_manifest,
    validate_script_action_result,
    validate_script_props,
    validate_script_status,
)

# CONTRACTS_DIR: another checkout of screenplan-contracts, such as a worktree
# whose schemas package is on PYTHONPATH.
EXAMPLES = Path(
    os.environ.get("CONTRACTS_DIR") or Path(__file__).resolve().parents[2] / "screenplan-contracts"
) / "examples"


def _load(name: str):
    return json.loads((EXAMPLES / name).read_text("utf-8"))


def test_script_status_example():
    out = validate_script_status(_load("script-status.example.json"))
    assert out.script_id


def test_event_status_example():
    out = validate_event_status(_load("event-status.example.json"))
    assert out.type == "sequence"


def test_script_action_log_example():
    out = validate_script_action_log(_load("script-action-log.example.json"))
    assert out.target_system == "python"
    assert out.pre_file is not None
    assert out.post_file is None  # `{}` collapses to None


def test_artifacts_spec_loads():
    spec = get_artifacts_spec()
    assert spec.version == 1
    assert "detectObject" in spec.actions
    assert spec.actions["scriptReference"].attributes is not None


def test_negative_script_status():
    with pytest.raises(ContractValidationError):
        validate_script_status({"script_id": "x"})


def test_script_action_result_example():
    out = validate_script_action_result(_load("script-action-result.example.json"))
    assert out.root.action == "detectObject"
    assert out.root.fields.matches[0].score == 0.909


def test_script_action_result_rejects_unknown_fields():
    data = _load("script-action-result.example.json")
    data["fields"]["typo_field"] = 1
    with pytest.raises(ContractValidationError):
        validate_script_action_result(data)


def test_script_action_result_for_an_action_without_fields():
    out = validate_script_action_result({
        "format": "screenplan.action-result", "version": 1,
        "action": "sleepStatement", "action_group": 3, "script_counter": 4, "fields": {},
    })
    assert out.root.action == "sleepStatement"



def test_script_props_example_with_agent_tool():
    out = validate_script_props(_load("script-props.example.json"))
    assert out.agent_tool.name == "open_app"
    assert out.agent_tool.effects.value == "changes-device"
    assert out.agent_tool.inputs["name"].model_dump()["type"] == "string"
    assert out.agent_tool.timeout_seconds == 120


def test_agent_tool_defaults():
    out = validate_agent_tool_manifest({"description": "Reads the clock.", "effects": "reads-device"})
    assert out.name is None
    assert out.inputs == {} and out.outputs == {}
    assert out.repeatable is False
    assert out.timeout_seconds == 600


@pytest.mark.parametrize("manifest", [
    {"effects": "reads-device"},
    {"description": "", "effects": "reads-device"},
    {"description": "x"},
    {"description": "x", "effects": "writes-disk"},
    {"description": "x", "effects": "reads-device", "name": "OpenApp"},
    {"description": "x", "effects": "reads-device", "name": "a" * 65},
    {"description": "x", "effects": "reads-device", "inputs": {"name": "string"}},
    {"description": "x", "effects": "reads-device", "timeoutSeconds": 0},
    {"description": "x", "effects": "reads-device", "timeoutSeconds": 7201},
    {"description": "x", "effects": "reads-device", "secrets": ["password"]},
], ids=[
    "no description", "empty description", "no effects", "unknown effects", "name with capitals",
    "name too long", "input schema not an object", "timeout 0", "timeout above 7200", "unknown key",
])
def test_agent_tool_rejects(manifest):
    with pytest.raises(ContractValidationError):
        validate_agent_tool_manifest(manifest)
    props = _load("script-props.example.json")
    props["agentTool"] = manifest
    with pytest.raises(ContractValidationError):
        validate_script_props(props)
