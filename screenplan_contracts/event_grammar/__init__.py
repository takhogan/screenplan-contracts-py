"""Scheduler grammar 2: the grammar checker (workspace docs/specs/scheduler-python-grammar.md).

An event's text is a small subset of Python, parsed with ``ast`` and never
executed. ``check(text, context=None)`` answers the result every entry point
answers (``event-check-result.schema.json`` in screenplan-contracts):

    {"ok", "grammar", "errors", "warnings", "unchecked", "outline"}

The grammar level needs the text only and is deterministic; the TypeScript
checker (``@screenplan/script-actions`` ``scheduler-grammar-v2``) gives the
same diagnostics for the same text, both pinned by the conformance corpus in
``screenplan-contracts/fixtures/event-grammar/``. The context level runs
when a ``context`` is given (the user's workspaces, scripts, hosts, devices,
saved events and host mappings) and adds what it can see; anything it can't
look up is reported as ``unchecked``.

Positions are 1-based lines and 1-based columns counted in Unicode code
points, the end exclusive.
"""
from __future__ import annotations

from .checker import (  # noqa: F401
    HEADER,
    check,
    has_header,
    is_grammar2,
    load_registry,
    outline,
    validate,
)

__all__ = ["HEADER", "check", "has_header", "is_grammar2", "load_registry", "outline", "validate"]
