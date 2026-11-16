"""ScreenPlan names: what a workspace or a script may be called.

Scheduler grammar 2 calls a script as ``Workspace.Script()``, so both names
must be Python identifiers. The rule (workspace docs/specs/scheduler-python-grammar.md,
"Names") applies wherever a name is created or changed; existing names that
fail it keep working for reading, running and updating.

The same rule lives in TypeScript as ``isScreenPlanName`` in
``@screenplan/script-vcs``, and both test suites read one fixture list,
``screenplan-contracts/fixtures/screenplan-names.json``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

__all__ = [
    "NOT_A_SCREENPLAN_NAME",
    "PYTHON_KEYWORDS",
    "RESERVED_SCRIPT_NAMES",
    "SCREENPLAN_NAME_MAX_LENGTH",
    "SCREENPLAN_NAME_MESSAGE",
    "SCREENPLAN_NAME_PATTERN",
    "SCREENPLAN_WORKSPACE_NAME_MESSAGE",
    "SCREENPLAN_WORKSPACE_NAME_PATTERN",
    "ScreenPlanNameProblem",
    "clashing_name",
    "is_screenplan_name",
    "screenplan_name_problem",
    "suggest_screenplan_name",
]

SCREENPLAN_NAME_MAX_LENGTH = 100
SCREENPLAN_NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_]{0,99}$"
SCREENPLAN_WORKSPACE_NAME_PATTERN = r"^[A-Z][A-Za-z0-9_]{0,99}$"

# keyword.kwlist + keyword.softkwlist of Python 3.12, written out so the rule
# doesn't change with the Python that runs it (3.11 has no soft keyword
# "type"). "_" is a soft keyword too, but the pattern already refuses it.
PYTHON_KEYWORDS = (
    "False", "None", "True", "and", "as", "assert", "async", "await", "break",
    "class", "continue", "def", "del", "elif", "else", "except", "finally", "for",
    "from", "global", "if", "import", "in", "is", "lambda", "nonlocal", "not", "or",
    "pass", "raise", "return", "try", "while", "with", "yield",
    "case", "match", "type",
)

RESERVED_SCRIPT_NAMES = ("testScript", "startDevice", "stopDevice")

NOT_A_SCREENPLAN_NAME = "not-a-screenplan-name"

SCREENPLAN_NAME_MESSAGE = (
    "A name is a letter followed by letters, digits or `_` (up to 100), and can't be a Python keyword."
)
SCREENPLAN_WORKSPACE_NAME_MESSAGE = (
    "A workspace name starts with a capital letter, followed by letters, digits or `_` (up to 100)."
)

# \Z, not $: "$" also matches before a trailing newline.
_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,99}\Z")
_KEYWORDS = frozenset(PYTHON_KEYWORDS)
_RESERVED = frozenset(RESERVED_SCRIPT_NAMES)


@dataclass(frozen=True)
class ScreenPlanNameProblem:
    """Why a name fails: ``reason`` is one of not-a-string, pattern, keyword,
    capital, reserved, clash. ``suggestion`` is the capitalized name for
    ``capital`` and the existing name for ``clash``."""

    reason: str
    message: str
    suggestion: Optional[str] = None
    code: str = NOT_A_SCREENPLAN_NAME


def is_screenplan_name(name: object, kind: str) -> bool:
    """Whether ``name`` may be given to a new or renamed workspace or script
    (``kind`` "workspace" or "script"). Doesn't look at other names: use
    ``screenplan_name_problem`` with ``existing`` for uniqueness."""
    return screenplan_name_problem(name, kind) is None


def screenplan_name_problem(
    name: object, kind: str, existing: Optional[Iterable[str]] = None
) -> Optional[ScreenPlanNameProblem]:
    """Why ``name`` fails the rule, or None. ``existing`` is the other names in
    its scope; a name equal to one ignoring case fails unless it is exactly it."""
    _check_kind(kind)
    rule = SCREENPLAN_WORKSPACE_NAME_MESSAGE if kind == "workspace" else SCREENPLAN_NAME_MESSAGE
    if not isinstance(name, str):
        return ScreenPlanNameProblem("not-a-string", rule)
    if not _NAME_RE.match(name):
        return ScreenPlanNameProblem("pattern", rule)
    if name in _KEYWORDS:
        return ScreenPlanNameProblem("keyword", f"`{name}` is a Python keyword. {SCREENPLAN_NAME_MESSAGE}")
    if kind == "workspace" and not ("A" <= name[0] <= "Z"):
        capitalized = name[0].upper() + name[1:]
        return ScreenPlanNameProblem("capital", f"{rule} Did you mean `{capitalized}`?", capitalized)
    if kind == "script" and name in _RESERVED:
        return ScreenPlanNameProblem("reserved", f"`{name}` is a system script's name. {SCREENPLAN_NAME_MESSAGE}")
    clash = clashing_name(name, existing)
    if clash is not None:
        scope = "workspace" if kind == "workspace" else "script in this workspace"
        return ScreenPlanNameProblem("clash", f"`{name}` differs only in case from the {scope} `{clash}`.", clash)
    return None


def clashing_name(name: str, existing: Optional[Iterable[str]] = None) -> Optional[str]:
    """The name in ``existing`` equal to ``name`` ignoring case but not exactly."""
    if not existing:
        return None
    lower = name.lower()
    for other in existing:
        if isinstance(other, str) and other != name and other.lower() == lower:
            return other
    return None


def suggest_screenplan_name(name: str, kind: str, existing: Optional[Iterable[str]] = None) -> str:
    """A name that passes, made from one that doesn't: invalid characters to
    ``_``, ``S_`` in front of a name that doesn't start with a letter, a
    workspace's first letter capitalized, a trailing ``_`` on a keyword or a
    system script's name, ``_2``, ``_3``… on a clash with ``existing``."""
    existing = list(existing or [])
    taken = {n.lower() for n in existing}
    if screenplan_name_problem(name, kind, existing) is None and name.lower() not in taken:
        return name
    s = re.sub(r"[^A-Za-z0-9_]", "_", str(name or ""))
    if not re.match(r"[A-Za-z]", s):
        s = "S_" + s
    if kind == "workspace":
        s = s[0].upper() + s[1:]
    s = s[:SCREENPLAN_NAME_MAX_LENGTH]
    if s in _KEYWORDS or (kind == "script" and s in _RESERVED):
        s = _fit(s, "_")
    if s.lower() in taken:
        n = 2
        while _fit(s, f"_{n}").lower() in taken:
            n += 1
        s = _fit(s, f"_{n}")
    return s


def _fit(base: str, suffix: str) -> str:
    return base[: SCREENPLAN_NAME_MAX_LENGTH - len(suffix)] + suffix


def _check_kind(kind: str) -> None:
    if kind not in ("workspace", "script"):
        raise ValueError(f"kind must be 'workspace' or 'script', not {kind!r}")
