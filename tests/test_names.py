"""The ScreenPlan name rule against the fixture list both implementations read."""
from __future__ import annotations

import json
import keyword
import os
from pathlib import Path

from screenplan_contracts.names import (
    NOT_A_SCREENPLAN_NAME,
    PYTHON_KEYWORDS,
    is_screenplan_name,
    screenplan_name_problem,
    suggest_screenplan_name,
)

CONTRACTS = Path(os.environ.get("CONTRACTS_DIR") or Path(__file__).resolve().parents[2] / "screenplan-contracts")
FIXTURES = json.loads((CONTRACTS / "fixtures" / "screenplan-names.json").read_text("utf-8"))


def test_good_names_pass():
    for e in FIXTURES["good"]:
        assert is_screenplan_name(e["name"], e["kind"]), e
        assert screenplan_name_problem(e["name"], e["kind"]) is None


def test_bad_names_fail_with_their_reason():
    for e in FIXTURES["bad"]:
        assert not is_screenplan_name(e["name"], e["kind"]), e
        p = screenplan_name_problem(e["name"], e["kind"])
        assert p.code == NOT_A_SCREENPLAN_NAME
        assert p.reason == e["reason"], e
        assert p.suggestion == e.get("suggestion"), e


def test_clash_ignoring_case():
    for e in FIXTURES["clash"]:
        p = screenplan_name_problem(e["name"], e["kind"], e["existing"])
        assert (p.reason if p else None) == e["reason"], e
        assert (p.suggestion if p else None) == e.get("suggestion"), e


def test_suggestions():
    for e in FIXTURES["suggest"]:
        s = suggest_screenplan_name(e["name"], e["kind"], e.get("existing"))
        assert s == e["suggestion"], e
        assert screenplan_name_problem(s, e["kind"], e.get("existing")) is None


def test_trailing_newline_fails():
    assert not is_screenplan_name("Default\n", "workspace")


def test_messages():
    assert "Did you mean `Ops`?" in screenplan_name_problem("ops", "workspace").message
    assert screenplan_name_problem("a-b", "script").message == (
        "A name is a letter followed by letters, digits or `_` (up to 100), and can't be a Python keyword."
    )


def test_keyword_list_covers_this_python():
    for k in keyword.kwlist + [k for k in keyword.softkwlist if k != "_"]:
        assert k in PYTHON_KEYWORDS, k
