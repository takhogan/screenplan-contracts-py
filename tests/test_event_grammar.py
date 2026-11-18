"""The grammar 2 checker against the conformance corpus that the TypeScript
checker also passes (screenplan-contracts/fixtures/event-grammar/).

UPDATE_CORPUS=1 rewrites the expected *.json from this checker; review the
diff, then run the TypeScript suite, which must agree."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from screenplan_contracts.validation import validate_event_check_result
from screenplan_contracts.event_grammar import HEADER, check, is_grammar2, load_registry, outline, validate

CONTRACTS = Path(os.environ.get("CONTRACTS_DIR") or Path(__file__).resolve().parents[2] / "screenplan-contracts")
CORPUS = CONTRACTS / "fixtures" / "event-grammar"
FIXTURES = sorted(p for p in CORPUS.glob("*.py"))


def context_of(path: Path):
    c = path.with_suffix(".context.json")
    return json.loads(c.read_text("utf-8")) if c.exists() else None


def comparable(result):
    """syntax-error diagnostics compare by code only: Python and Lezer place them differently."""
    out = json.loads(json.dumps(result))
    for key in ("errors", "warnings"):
        out[key] = [{"code": d["code"]} if d["code"] == "syntax-error" else d for d in out[key]]
    return out


@pytest.mark.parametrize("path", FIXTURES, ids=[p.name for p in FIXTURES])
def test_corpus(path: Path):
    result = check(path.read_text("utf-8"), context_of(path))
    expected_path = path.with_suffix(".json")
    if os.environ.get("UPDATE_CORPUS"):
        expected_path.write_text(json.dumps({"result": result}, indent=2, ensure_ascii=False) + "\n", "utf-8")
    expected = json.loads(expected_path.read_text("utf-8"))["result"]
    assert comparable(result) == comparable(expected)
    validate_event_check_result(result)


def test_every_code_is_exercised():
    seen = set()
    for path in FIXTURES:
        r = json.loads(path.with_suffix(".json").read_text("utf-8"))["result"]
        for key in ("errors", "warnings", "unchecked"):
            seen.update(d["code"] for d in r[key])
    codes = {d["code"] for d in load_registry()["diagnostics"]}
    assert codes - seen == set()


def test_registry_names_start_lowercase():
    reg = load_registry()
    names = [b["name"] for b in reg["builtins"]] + [f["name"] for f in reg["functions"]] + [m["name"] for m in reg["modules"]]
    names.append(reg["loopFunction"]["name"])
    for name in names:
        assert re.match(r"^[a-z]", name), name
    for b in reg["builtins"]:
        for p in b["params"]:
            assert re.match(r"^[a-z]", p["name"]), (b["name"], p["name"])


def test_codes_are_kebab_case_and_unique():
    codes = [d["code"] for d in load_registry()["diagnostics"]]
    assert len(codes) == len(set(codes))
    for c in codes:
        assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", c)


def apply_fixes(text: str, diags) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)
    flat = "\n".join(lines)
    fixes = sorted((d for d in diags if "fix" in d), key=lambda d: (d["line"], d["column"]), reverse=True)
    for d in fixes:
        start = offsets[d["line"] - 1] + d["column"] - 1
        end = offsets[d["endLine"] - 1] + d["endColumn"] - 1
        flat = flat[:start] + d["fix"]["replace"] + flat[end:]
    return flat


@pytest.mark.parametrize("path", FIXTURES, ids=[p.name for p in FIXTURES])
def test_applying_fixes_clears_them(path: Path):
    text = path.read_text("utf-8")
    result = check(text, context_of(path))
    fixed = [d for d in result["errors"] if "fix" in d]
    if not fixed:
        return
    after = check(apply_fixes(text, fixed), context_of(path))
    remaining = {(d["code"], d["message"]) for d in after["errors"]}
    for d in fixed:
        assert (d["code"], d["message"]) not in remaining, d


def test_entry_points_agree():
    text = (CORPUS / "01-spec-example.py").read_text("utf-8")
    assert is_grammar2(text)
    assert not is_grammar2((CORPUS / "16-grammar1.py").read_text("utf-8"))
    g1 = check((CORPUS / "16-grammar1.py").read_text("utf-8"))
    assert g1["grammar"] == 1
    assert [(e["code"], "fix" in e) for e in g1["errors"]] == [("grammar-1-not-accepted", False)]
    assert validate(text) == []
    assert outline(text) == check(text)["outline"]
    assert check("\r\n".join([HEADER, "with target_host('H'):", "    Default.Run()"]))["ok"]


def test_cli(tmp_path):
    env = dict(os.environ)
    ok = subprocess.run([sys.executable, "-m", "screenplan_contracts.event_grammar", "check", str(CORPUS / "01-spec-example.py")],
                        capture_output=True, text=True, env=env)
    assert ok.returncode == 0, ok.stderr
    assert json.loads(ok.stdout)["ok"] is True
    bad = subprocess.run([sys.executable, "-m", "screenplan_contracts.event_grammar", "check", str(CORPUS / "19-context.py"),
                          "--context", str(CORPUS / "19-context.context.json")], capture_output=True, text=True, env=env)
    assert bad.returncode == 1
    assert json.loads(bad.stdout) == check((CORPUS / "19-context.py").read_text("utf-8"), context_of(CORPUS / "19-context.py"))


def test_a_todo_comment_is_an_error():
    r = check(HEADER + "\n    # TODO(grammar 1): if(x, Foo) -- why\npass\n")
    assert [(e["code"], e["line"], e["column"], e["endColumn"]) for e in r["errors"]][:1] == [("grammar-1-todo", 2, 5, 41)]
    assert check(HEADER + "\n# TODO: something else\npass\n")["ok"] is True
