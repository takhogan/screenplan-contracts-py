"""Smoke tests for shared_contracts: validate every example JSON."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from screenplan_contracts import (
    ContractValidationError,
    get_artifacts_spec,
    validate_event_status,
    validate_script_action_log,
    validate_script_status,
)

EXAMPLES = Path(__file__).resolve().parents[2] / "screenplan-contracts" / "examples"


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
