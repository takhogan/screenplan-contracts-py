"""The grammar 2 checker on Python's ``ast``. Mirrored line for line by
``scheduler-grammar-v2.ts`` in @screenplan/script-actions; a change to one is a
change to the other and to the conformance corpus."""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, replace as dc_replace
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..names import screenplan_name_problem

HEADER = "# ScreenPlan event (grammar 2)"
REGISTRY_FILE = "event-grammar-builtins.json"

Range = Tuple[int, int, int, int]


@lru_cache(maxsize=1)
def load_registry() -> Dict[str, Any]:
    """The built-in registry, shipped in screenplan-contracts-schemas."""
    from screenplan_contracts_schemas import schema_text

    return json.loads(schema_text(REGISTRY_FILE))


class _Registry:
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.header = data["header"]
        self.max_loop = data["limits"]["maxLoopIterations"]
        self.max_calls = data["limits"]["maxScriptCalls"]
        self.slot_re = re.compile(data["slots"]["pattern"])
        self.builtins = {b["name"]: b for b in data["builtins"]}
        self.order = [b["name"] for b in data["builtins"] if b["kind"] in ("statement", "context")]
        self.functions = {f["name"] for f in data["functions"]}
        self.loop_function = data["loopFunction"]["name"]
        self.modules = {m["name"]: m for m in data["modules"]}
        self.module_calls = set()
        for m in data["modules"]:
            for c in m.get("calls", []):
                self.module_calls.add(c)
            if isinstance(m["attributes"], list) and "calls" not in m:
                for a in m["attributes"]:
                    self.module_calls.add(f"{m['name']}.{a}")
        self.removed = data.get("grammar1Removed", {})
        self.templates = {d["code"]: d for d in data["diagnostics"]}
        self.reserved = set(self.builtins) | self.functions | set(self.modules) | {self.loop_function}

    def kind(self, name: str) -> Optional[str]:
        b = self.builtins.get(name)
        return b["kind"] if b else None

    def module_call_allowed(self, dotted: str) -> bool:
        root = dotted.split(".")[0]
        m = self.modules.get(root)
        if not m:
            return False
        if m["attributes"] == "*":
            return dotted.count(".") == 1
        return dotted in self.module_calls

    def module_attr_allowed(self, dotted: str) -> bool:
        parts = dotted.split(".")
        m = self.modules.get(parts[0])
        if not m or len(parts) < 2:
            return False
        if m["attributes"] == "*":
            return len(parts) == 2
        if len(parts) == 2:
            return parts[1] in m["attributes"]
        return dotted in self.module_calls


@lru_cache(maxsize=1)
def _registry() -> _Registry:
    return _Registry(load_registry())


# ---------------------------------------------------------------------------
# text


def _normalize(text: str) -> str:
    if text.startswith("﻿"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


class _Source:
    def __init__(self, text: str):
        self.text = text
        self.lines = text.split("\n")
        self._bytes = [line.encode("utf-8") for line in self.lines]

    def col(self, lineno: int, byte_offset: int) -> int:
        """1-based code-point column of a byte offset into a line."""
        if lineno < 1 or lineno > len(self.lines):
            return 1
        return len(self._bytes[lineno - 1][:byte_offset].decode("utf-8", "ignore")) + 1

    def rng(self, node: ast.AST) -> Range:
        return (
            node.lineno,
            self.col(node.lineno, node.col_offset),
            node.end_lineno,
            self.col(node.end_lineno, node.end_col_offset),
        )

    def kw(self, node: ast.AST, word: str) -> Range:
        c = self.col(node.lineno, node.col_offset)
        return (node.lineno, c, node.lineno, c + len(word))

    def attr_range(self, node: ast.Attribute) -> Range:
        end = self.col(node.end_lineno, node.end_col_offset)
        return (node.end_lineno, end - len(node.attr), node.end_lineno, end)

    def slice(self, r: Range) -> str:
        l1, c1, l2, c2 = r
        if l1 == l2:
            return self.lines[l1 - 1][c1 - 1 : c2 - 1]
        out = [self.lines[l1 - 1][c1 - 1 :]]
        out.extend(self.lines[l1 : l2 - 1])
        out.append(self.lines[l2 - 1][: c2 - 1])
        return "\n".join(out)

    def src(self, node: ast.AST) -> str:
        return self.slice(self.rng(node))

    def def_name_range(self, node: ast.FunctionDef) -> Range:
        c = self.col(node.lineno, node.col_offset)
        line = self.lines[node.lineno - 1]
        m = re.compile(r"def\s+").match(line, c - 1)
        start = (m.end() if m else c + 3) + 1
        return (node.lineno, start, node.lineno, start + len(node.name))

    def decorator_range(self, node: ast.AST) -> Range:
        l1, c1, l2, c2 = self.rng(node)
        line = self.lines[l1 - 1]
        at = line.rfind("@", 0, c1 - 1)
        return (l1, (at + 1) if at >= 0 else c1, l2, c2)


# ---------------------------------------------------------------------------
# header


_BLOCK_RE = re.compile(r"^\s*(with|def|for|try|if|elif|else|finally|while)\b(?!\s*\().*:\s*(#.*)?$")
_SCRIPT_RE = re.compile(r"^\s*[A-Z][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\s*\(")


def _header_state(lines: List[str]) -> Tuple[str, Optional[int]]:
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        if s == HEADER:
            return "ok", i
        if s.startswith("#") and "screenplan event" in s.lower():
            return "malformed", i
        return "none", i
    return "none", None


def _looks_grammar2(lines: List[str]) -> bool:
    reg = _registry()
    names = sorted((b for b in reg.builtins if reg.builtins[b]["kind"] != "expression"), key=len, reverse=True)
    builtin_re = re.compile(r"(^|[^A-Za-z0-9_.])(" + "|".join(names) + r")\s*\(")
    for line in lines:
        if _BLOCK_RE.search(line) or _SCRIPT_RE.search(line) or builtin_re.search(line):
            return True
    return False


def is_grammar2(text: str) -> bool:
    """Whether the text's first non-blank line is the grammar 2 header."""
    return _header_state(_normalize(text).split("\n"))[0] == "ok"


# ---------------------------------------------------------------------------
# diagnostics


def _levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _norm(name: str) -> str:
    return name.lower().replace("_", "")


@dataclass
class _State:
    in_def: Optional[str] = None
    module_top: bool = True
    top_chain: bool = True
    parallel: bool = False
    mult: int = 1
    hosts: Any = None  # None: no target_host; list of literal names; "unknown"
    wrapped: bool = False


_BINOPS = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**",
}
_BAD_BINOPS = {
    ast.MatMult: "@", ast.LShift: "<<", ast.RShift: ">>", ast.BitOr: "|", ast.BitXor: "^", ast.BitAnd: "&",
}
_DURATION_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?$")

_KEYWORD_STATEMENTS = [
    (ast.While, "`while`", "while", ": use a `for` with a written count, or loop inside a script (a scriptReference with runMode run)"),
    (ast.Import, "`import`", "import", ": events use only the built-ins, random, math and datetime"),
    (ast.ImportFrom, "`import`", "from", ": events use only the built-ins, random, math and datetime"),
    (ast.ClassDef, "`class`", "class", ""),
    (ast.Return, "`return`", "return", ""),
    (ast.Global, "`global`", "global", ""),
    (ast.Nonlocal, "`nonlocal`", "nonlocal", ""),
    (ast.Delete, "`del`", "del", ""),
    (ast.Assert, "`assert`", "assert", ""),
    (ast.Raise, "`raise`", "raise", ""),
    (ast.Break, "`break`", "break", ""),
    (ast.Continue, "`continue`", "continue", ""),
    (ast.AsyncFunctionDef, "`async`", "async", ""),
    (ast.AsyncFor, "`async`", "async", ""),
    (ast.AsyncWith, "`async`", "async", ""),
]
if hasattr(ast, "Match"):
    _KEYWORD_STATEMENTS.append((ast.Match, "`match`", "match", ""))


class _Checker:
    def __init__(self, src: _Source, tree: ast.Module):
        self.src = src
        self.tree = tree
        self.reg = _registry()
        self.diags: List[Dict[str, Any]] = []
        self.defs: Dict[str, ast.FunctionDef] = {}
        self.def_params: Dict[str, List[str]] = {}
        self.top_vars: set = set()
        self.def_vars: Dict[str, set] = {}
        self.sites: List[Tuple[str, Range, str, Optional[str]]] = []  # name, range, kind, scope
        self.loads: Dict[Optional[str], set] = {}
        self.used_workspaces: set = set()
        self.counts: Dict[Optional[str], int] = {}
        self.edges: List[Tuple[Optional[str], str, Range, int]] = []
        self.try_count = 0
        self.script_calls: List[Dict[str, Any]] = []
        self.devices: List[Dict[str, Any]] = []
        self.host_literals: List[Tuple[str, Range]] = []
        self.run_events: List[Dict[str, Any]] = []
        self.unwrapped: List[Range] = []

    # -- diagnostics -------------------------------------------------------

    def add(self, code: str, r: Range, fix: Optional[Dict[str, str]] = None, **values: Any) -> None:
        template = self.reg.templates[code]["message"]
        message = template.format(**values)
        d = {"code": code, "line": r[0], "column": r[1], "endLine": r[2], "endColumn": r[3], "message": message}
        if fix is not None:
            d["fix"] = fix
        self.diags.append(d)

    # -- scopes ------------------------------------------------------------

    def collect(self) -> None:
        for s in self.tree.body:
            if isinstance(s, ast.FunctionDef):
                if s.name in self.defs:
                    self.add("duplicate-def", self.src.def_name_range(s), name=s.name)
                else:
                    self.defs[s.name] = s
                    self.def_params[s.name] = [a.arg for a in s.args.args]
        self.top_vars = self._assigned(self.tree.body, top=True)
        for name, d in self.defs.items():
            names = self._assigned(d.body, top=False)
            names.update(a.arg for a in d.args.args)
            self.def_vars[name] = names

    def _assigned(self, stmts: List[ast.stmt], top: bool) -> set:
        out: set = set()
        stack = list(stmts)
        while stack:
            s = stack.pop()
            if isinstance(s, ast.FunctionDef) and top:
                continue
            if isinstance(s, ast.Assign) and len(s.targets) == 1 and isinstance(s.targets[0], ast.Name):
                out.add(s.targets[0].id)
            if isinstance(s, ast.For) and isinstance(s.target, ast.Name):
                out.add(s.target.id)
            for field in ("body", "orelse", "finalbody"):
                stack.extend(getattr(s, field, []) or [])
            for h in getattr(s, "handlers", []) or []:
                stack.extend(h.body)
        return out

    def visible(self, st: _State) -> set:
        if st.in_def is None:
            return self.top_vars
        return self.top_vars | self.def_vars.get(st.in_def, set())

    def site(self, name: str, r: Range, kind: str, st: _State) -> None:
        self.sites.append((name, r, kind, st.in_def))
        if name in self.reg.reserved:
            self.add("reserved-name", r, name=name)

    # -- statements --------------------------------------------------------

    def run(self) -> None:
        self.collect()
        self.body(self.tree.body, _State())
        for name, r, kind, scope in self.sites:
            if name in self.used_workspaces:
                self.add("name-hides-workspace", r, name=name)
        self.check_recursion()
        total = self.total_calls()
        if total > self.reg.max_calls:
            first = self.src.lines[0] if self.src.lines else ""
            self.add("too-many-script-calls", (1, 1, 1, len(first) + 1), count=total)

    def body(self, stmts: List[ast.stmt], st: _State) -> None:
        for s in stmts:
            self.stmt(s, st)

    def stmt(self, s: ast.stmt, st: _State) -> None:
        if isinstance(s, ast.Expr):
            self.expr_stmt(s, st)
        elif isinstance(s, ast.Assign):
            self.assign(s, st)
        elif isinstance(s, ast.AugAssign):
            self.add("unsupported-statement", self.src.rng(s), construct="Augmented assignment (`x += …`)", hint=": write `x = x + …`")
        elif isinstance(s, ast.AnnAssign):
            self.add("unsupported-statement", self.src.rng(s), construct="An annotated assignment", hint="")
        elif isinstance(s, ast.FunctionDef):
            self.funcdef(s, st)
        elif isinstance(s, ast.If):
            self.if_(s, st)
        elif isinstance(s, ast.For):
            self.for_(s, st)
        elif isinstance(s, ast.With):
            self.with_(s, st)
        elif isinstance(s, ast.Try):
            self.try_(s, st)
        elif isinstance(s, ast.Pass):
            pass
        else:
            for cls, construct, word, hint in _KEYWORD_STATEMENTS:
                if isinstance(s, cls):
                    self.add("unsupported-statement", self.src.kw(s, word), construct=construct, hint=hint)
                    return
            self.add("unsupported-statement", self.src.rng(s), construct=f"`{type(s).__name__}`", hint="")

    def expr_stmt(self, s: ast.Expr, st: _State) -> None:
        v = s.value
        if not isinstance(v, ast.Call):
            self.add("expression-statement", self.src.rng(v))
            return
        if not st.wrapped and st.in_def is None:
            self.unwrapped.append(self.src.rng(v))
        f = v.func
        if isinstance(f, ast.Name):
            n = f.id
            kind = self.reg.kind(n)
            if kind == "statement":
                if st.parallel and n in ("delay_start", "wait_until", "dropout_chance", "run_event"):
                    self.add("not-allowed-in-parallel", self.src.rng(v), construct=f"`{n}()`")
                bound, extras = self.builtin_call(v, self.reg.builtins[n], st)
                if n == "run_event":
                    self.record_run_event(v, bound, extras)
                elif n in ("start_device", "stop_device"):
                    self.record_device(bound, st, one_argument=False)
            elif kind == "context":
                self.add("context-as-statement", self.src.rng(f), name=n)
            elif n == "parameter":
                self.add("parameter-not-assigned", self.src.rng(v))
            elif n in self.reg.functions or n == self.reg.loop_function:
                self.add("value-as-statement", self.src.rng(v), name=n)
            elif n in self.defs:
                self.sequence_call(v, n, st)
            else:
                self.unknown_call(f, n, "statement")
        elif isinstance(f, ast.Attribute):
            self.script_call(v, st)
        else:
            self.add("not-a-script-call", self.src.rng(f))

    def script_call(self, v: ast.Call, st: _State) -> None:
        f = v.func
        base = f.value
        if not isinstance(base, ast.Name):
            dotted = self.dotted(f)
            if dotted and dotted.split(".")[0] in self.reg.modules:
                self.add("value-as-statement", self.src.rng(v), name=dotted)
            else:
                self.add("not-a-script-call", self.src.rng(f))
            return
        ws = base.id
        if ws in self.reg.modules:
            self.add("value-as-statement", self.src.rng(v), name=f"{ws}.{f.attr}")
            return
        problem = screenplan_name_problem(ws, "workspace")
        if problem is not None:
            fix = None
            if problem.reason == "capital" and problem.suggestion and screenplan_name_problem(problem.suggestion, "workspace") is None:
                fix = {"replace": problem.suggestion, "label": f"did you mean {problem.suggestion}?"}
            self.add("bad-workspace-name", self.src.rng(base), fix, name=ws)
            return
        script = f.attr
        if screenplan_name_problem(script, "script") is not None:
            self.add("bad-script-name", self.src.attr_range(f), name=script)
            return
        self.used_workspaces.add(ws)
        call = f"{ws}.{script}"
        for a in v.args:
            if isinstance(a, ast.Starred):
                self.add("unsupported-expression", self.src.rng(a), construct="`*` unpacking", hint="")
            else:
                self.add("positional-argument", self.src.rng(a), name=call, why="inputs have no order")
        keywords = []
        for k in v.keywords:
            if k.arg is None:
                self.add("unsupported-expression", self.src.rng(k.value), construct="`**` unpacking", hint="")
                continue
            keywords.append(k.arg)
            self.expr(k.value, st)
        self.count(st)
        self.script_calls.append({"ws": ws, "script": script, "keywords": keywords, "range": self.src.rng(v), "hosts": st.hosts})

    def sequence_call(self, v: ast.Call, n: str, st: _State) -> None:
        if st.parallel:
            self.add("not-allowed-in-parallel", self.src.rng(v), construct=f"`{n}()`")
        params = self.def_params.get(n, [])
        for a in v.args:
            if isinstance(a, ast.Starred):
                self.add("unsupported-expression", self.src.rng(a), construct="`*` unpacking", hint="")
            else:
                self.add("positional-argument", self.src.rng(a), name=n, why="pass a sequence's parameters by name")
        for k in v.keywords:
            if k.arg is None:
                self.add("unsupported-expression", self.src.rng(k.value), construct="`**` unpacking", hint="")
                continue
            if k.arg not in params:
                self.add("unknown-keyword", self.src.rng(k), name=n, keyword=k.arg)
            self.expr(k.value, st)
        self.edges.append((st.in_def, n, self.src.rng(v), st.mult))

    def unknown_call(self, f: ast.Name, n: str, where: str) -> None:
        reg = self.reg
        suggestion = None
        for name in reg.order:
            b = reg.builtins[name]
            if n == b.get("grammar1") or _norm(n) == _norm(name):
                suggestion = name
                break
        if suggestion is None and n not in reg.removed:
            candidates = reg.order + [d for d in self.defs]
            best, best_names = 3, []
            for c in candidates:
                d = _levenshtein(n.lower(), c.lower())
                if d < best:
                    best, best_names = d, [c]
                elif d == best and c not in best_names:
                    best_names.append(c)
            if best <= 2 and len(best_names) == 1:
                suggestion = best_names[0]
        r = self.src.rng(f)
        if suggestion is not None:
            fix = {"replace": suggestion, "label": f"did you mean {suggestion}?"}
            if suggestion in self.defs:
                self.add("undefined-sequence", r, fix, name=n)
            else:
                self.add("unknown-builtin", r, fix, name=n, hint="")
        elif n in reg.removed:
            self.add("unknown-builtin", r, name=n, hint=f": {reg.removed[n]}")
        elif where == "with":
            self.add("unknown-builtin", r, name=n, hint=": the contexts are target_host, target_device, timeout, parallel and restart_device_on_crash")
        else:
            self.add("undefined-sequence", r, name=n)

    def builtin_call(self, call: ast.Call, b: Dict[str, Any], st: _State) -> Tuple[Dict[str, ast.expr], List[ast.keyword]]:
        name = b["name"]
        params = b["params"]
        positional = [p for p in params if not p.get("keywordOnly")]
        by_name = {p["name"]: p for p in params}
        bound: Dict[str, ast.expr] = {}
        extras: List[ast.keyword] = []
        extra_reported = False
        for i, a in enumerate(call.args):
            if isinstance(a, ast.Starred):
                self.add("unsupported-expression", self.src.rng(a), construct="`*` unpacking", hint="")
                continue
            if i < len(positional):
                bound[positional[i]["name"]] = a
                continue
            if b.get("duration") and isinstance(a, ast.Constant) and isinstance(a.value, str) and _DURATION_RE.match(a.value) and a.value:
                m = _DURATION_RE.match(a.value)
                parts = []
                if m.group(1) and int(m.group(1)):
                    parts.append(f"hours={int(m.group(1))}")
                if m.group(2) and int(m.group(2)):
                    parts.append(f"minutes={int(m.group(2))}")
                if not parts:
                    parts.append("minutes=0")
                replacement = ", ".join(parts)
                self.add("duration-string", self.src.rng(a), {"replace": replacement, "label": f"write {replacement}"}, value=a.value)
                extra_reported = True
                continue
            if not extra_reported:
                n = len(positional)
                self.add("too-many-arguments", self.src.rng(a), name=name, count=n, plural="" if n == 1 else "s")
                extra_reported = True
            self.expr(a, st)
        for k in call.keywords:
            if k.arg is None:
                self.add("unsupported-expression", self.src.rng(k.value), construct="`**` unpacking", hint="")
                continue
            if k.arg in by_name:
                if k.arg in bound:
                    self.add("duplicate-argument", self.src.rng(k), name=name, param=k.arg)
                    self.expr(k.value, st)
                else:
                    bound[k.arg] = k.value
            elif b.get("extraKeywords"):
                extras.append(k)
                self.expr(k.value, st)
            else:
                self.add("unknown-keyword", self.src.rng(k), name=name, keyword=k.arg)
                self.expr(k.value, st)
        one_argument = b.get("oneArgument")
        one_mode = bool(one_argument) and len(bound) == 1 and positional and positional[0]["name"] in bound and len(call.args) == 1
        if one_mode:
            bound = {one_argument: bound[positional[0]["name"]]}
        call_range = self.src.rng(call)
        for p in params:
            if p.get("required") and p["name"] not in bound and not (one_mode and p["name"] == positional[0]["name"]):
                self.add("missing-argument", call_range, name=name, param=p["name"])
        if b.get("atLeastOne") and not bound and not extra_reported:
            self.add("missing-argument", call_range, name=name, param="` or `".join(p["name"] for p in params))
        for pname, node in bound.items():
            p = by_name[pname]
            self.expr(node, st)
            if p.get("literal") and not self.is_literal(node):
                self.add("argument-must-be-literal", self.src.rng(node), name=name, param=pname)
                continue
            expected = self.type_problem(p, node)
            if expected is not None:
                fix = None
                if p.get("enum") and isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for option in p["enum"]:
                        if _norm(option) == _norm(node.value):
                            fix = {"replace": f"'{option}'", "label": f"did you mean '{option}'?"}
                            break
                self.add("wrong-argument-type", self.src.rng(node), fix, name=name, param=pname, expected=expected)
                continue
            if p.get("slot") and not one_mode and isinstance(node, ast.Constant) and isinstance(node.value, str) and not self.reg.slot_re.match(node.value):
                self.add("bad-slot", self.src.rng(node), value=node.value)
        if name == "parameter":
            kind = bound.get("kind")
            if isinstance(kind, ast.Constant) and kind.value in ("select", "multiple_select") and "options" not in bound:
                self.add("missing-argument", call_range, name=name, param="options")
        return bound, extras

    def literal_kind(self, node: ast.expr) -> Optional[str]:
        if isinstance(node, ast.JoinedStr):
            return "string"
        if isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, bool):
                return "bool"
            if isinstance(v, str):
                return "string"
            if isinstance(v, (int, float)):
                return "number"
            if v is None:
                return "none"
            return "other"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)) and self.literal_kind(node.operand) == "number":
            return "number"
        if isinstance(node, (ast.List, ast.Tuple)):
            return "list"
        if isinstance(node, ast.Dict):
            return "dict"
        return None

    def is_literal(self, node: ast.expr) -> bool:
        if isinstance(node, ast.Constant):
            return True
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return isinstance(node.operand, ast.Constant)
        if isinstance(node, (ast.List, ast.Tuple)):
            return all(self.is_literal(e) for e in node.elts)
        return False

    def type_problem(self, p: Dict[str, Any], node: ast.expr) -> Optional[str]:
        t = p.get("type", "any")
        kind = self.literal_kind(node)
        if p.get("enum") and kind == "string" and isinstance(node, ast.Constant) and node.value not in p["enum"]:
            return "one of " + ", ".join(f"'{o}'" for o in p["enum"])
        if kind is None or t == "any":
            return None
        if t == "string":
            return None if kind == "string" else "a string"
        if t == "number":
            return None if kind == "number" else "a number"
        if t == "list":
            return None if kind == "list" else "a list"
        if t == "string|strings":
            if kind == "string":
                return None
            if kind == "list" and all(self.literal_kind(e) in (None, "string") for e in node.elts):
                return None
            return "a string or a list of strings"
        return None

    def assign(self, s: ast.Assign, st: _State) -> None:
        if len(s.targets) > 1:
            self.add("unsupported-statement", self.src.rng(s), construct="Assigning several names at once (`a = b = …`)", hint="")
            return
        t = s.targets[0]
        if not isinstance(t, ast.Name):
            construct = {
                ast.Tuple: "Unpacking (`a, b = …`)", ast.List: "Unpacking (`[a, b] = …`)",
                ast.Attribute: "Assigning to an attribute", ast.Subscript: "Assigning to a subscript",
            }.get(type(t), "This assignment")
            self.add("unsupported-statement", self.src.rng(t), construct=construct, hint="")
            return
        self.site(t.id, self.src.rng(t), "variable", st)
        v = s.value
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "parameter":
            if st.in_def is not None:
                self.add("parameter-not-assigned", self.src.rng(v))
            else:
                self.builtin_call(v, self.reg.builtins["parameter"], st)
            return
        self.expr(v, st)

    def funcdef(self, s: ast.FunctionDef, st: _State) -> None:
        if not st.module_top:
            self.add("misplaced-def", self.src.kw(s, "def"))
            return
        for d in s.decorator_list:
            self.add("unsupported-statement", self.src.decorator_range(d), construct="A decorator", hint="")
        if s.returns is not None:
            self.add("unsupported-statement", self.src.rng(s.returns), construct="A return annotation", hint="")
        a = s.args
        for p in list(getattr(a, "posonlyargs", [])) + ([a.vararg] if a.vararg else []) + list(a.kwonlyargs) + ([a.kwarg] if a.kwarg else []):
            self.add("def-parameter", self.src.rng(p), why="`*args`, `**kwargs`, `/` and `*` aren't allowed")
        top = _State()
        n_plain = len(a.args) - len(a.defaults)
        for i, p in enumerate(a.args):
            if p.annotation is not None:
                self.add("def-parameter", self.src.rng(p.annotation), why="annotations aren't allowed")
            if i < n_plain:
                self.add("def-parameter", self.src.rng(p), why=f"`{p.arg}` needs a default")
            self.site(p.arg, self.src.rng(p) if p.annotation is None else (p.lineno, self.src.col(p.lineno, p.col_offset), p.lineno, self.src.col(p.lineno, p.col_offset) + len(p.arg)), "param", _State(in_def=s.name))
        for dflt in a.defaults:
            self.expr(dflt, top)
        if self.defs.get(s.name) is s:
            self.site(s.name, self.src.def_name_range(s), "def", top)
        self.body(s.body, _State(in_def=s.name, module_top=False, top_chain=False, hosts="unknown", wrapped=True))

    def if_(self, s: ast.If, st: _State) -> None:
        self.expr(s.test, st)
        inner = dc_replace(st, module_top=False, top_chain=False)
        self.body(s.body, inner)
        self.body(s.orelse, inner)

    def for_(self, s: ast.For, st: _State) -> None:
        if isinstance(s.target, ast.Name):
            self.site(s.target.id, self.src.rng(s.target), "loop", st)
        else:
            self.add("unsupported-statement", self.src.rng(s.target), construct="Unpacking in a `for`", hint="")
        if s.orelse:
            self.add("loop-else", self.src.kw(s, "for"))
        count = self.loop_count(s.iter, st)
        if count is not None and count > self.reg.max_loop:
            self.add("loop-too-long", self.src.rng(s.iter), count=count)
        inner = dc_replace(st, module_top=False, top_chain=False, mult=st.mult * (count if count is not None else 1))
        self.body(s.body, inner)

    def int_literal(self, node: ast.expr) -> Optional[int]:
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = self.int_literal(node.operand)
            if v is not None and isinstance(node.operand, ast.Constant):
                return -v if isinstance(node.op, ast.USub) else v
        return None

    def loop_count(self, it: ast.expr, st: _State) -> Optional[int]:
        if isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == self.reg.loop_function:
            if it.keywords or not (1 <= len(it.args) <= 3):
                self.add("loop-count-not-written", self.src.rng(it))
                return None
            values = [self.int_literal(a) for a in it.args]
            if any(v is None for v in values):
                self.add("loop-count-not-written", self.src.rng(it))
                return None
            if len(values) == 3 and values[2] == 0:
                self.add("wrong-argument-type", self.src.rng(it.args[2]), name="range", param="step", expected="a number other than 0")
                return None
            return len(range(*values))
        if isinstance(it, (ast.List, ast.Tuple)):
            for e in it.elts:
                if isinstance(e, ast.Starred):
                    self.add("unsupported-expression", self.src.rng(e), construct="`*` unpacking", hint="")
                else:
                    self.expr(e, st)
            return len(it.elts)
        self.add("loop-count-not-written", self.src.rng(it))
        return None

    def with_(self, s: ast.With, st: _State) -> None:
        if st.parallel:
            self.add("not-allowed-in-parallel", self.src.kw(s, "with"), construct="A nested `with`")
        inner = dc_replace(st, module_top=False)
        for item in s.items:
            e = item.context_expr
            if item.optional_vars is not None:
                self.add("unsupported-statement", self.src.rng(item.optional_vars), construct="`with … as`", hint="")
            if not (isinstance(e, ast.Call) and isinstance(e.func, ast.Name)):
                self.add("unsupported-statement", self.src.rng(e), construct="A `with` on something other than a context", hint="")
                continue
            n = e.func.id
            kind = self.reg.kind(n)
            if kind == "context":
                bound, _ = self.builtin_call(e, self.reg.builtins[n], st)
                if n == "parallel":
                    inner.parallel = True
                elif n == "target_host":
                    inner.hosts = self.host_names(bound.get("names"))
                    inner.wrapped = True
                elif n == "target_device":
                    self.record_device(bound, inner, one_argument=True)
                elif n == "restart_device_on_crash":
                    self.record_device(bound, inner, one_argument=True)
            elif kind == "statement":
                self.add("statement-as-context", self.src.rng(e.func), name=n)
            else:
                self.unknown_call(e.func, n, "with")
        self.body(s.body, inner)

    def try_(self, s: ast.Try, st: _State) -> None:
        r = self.src.kw(s, "try")
        self.try_count += 1
        if self.try_count > 1:
            self.add("second-try", r)
        elif not st.top_chain:
            self.add("try-not-at-top", r)
        if st.parallel:
            self.add("not-allowed-in-parallel", r, construct="`try`")
        for h in s.handlers:
            self.add("unsupported-statement", self.src.kw(h, "except"), construct="`except`", hint=": only `try`/`finally` for now; failure handling comes later")
        if s.orelse:
            self.add("unsupported-statement", r, construct="`else` on a `try`", hint="")
        inner = dc_replace(st, module_top=False, top_chain=False)
        self.body(s.body, inner)
        self.body(s.finalbody, inner)

    def count(self, st: _State) -> None:
        self.counts[st.in_def] = self.counts.get(st.in_def, 0) + st.mult

    # -- context records ---------------------------------------------------

    def host_names(self, node: Optional[ast.expr]) -> Any:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            self.host_literals.append((node.value, self.src.rng(node)))
            return [node.value]
        if isinstance(node, (ast.List, ast.Tuple)) and node.elts and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts):
            for e in node.elts:
                self.host_literals.append((e.value, self.src.rng(e)))
            return [e.value for e in node.elts]
        return "unknown"

    def record_device(self, bound: Dict[str, ast.expr], st: _State, one_argument: bool) -> None:
        node = bound.get("name")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            self.devices.append({"device": node.value, "range": self.src.rng(node), "hosts": st.hosts})

    def record_run_event(self, call: ast.Call, bound: Dict[str, ast.expr], extras: List[ast.keyword]) -> None:
        path = bound.get("path")
        if isinstance(path, ast.Constant) and isinstance(path.value, str):
            self.run_events.append({"path": path.value, "range": self.src.rng(path), "keywords": [(k.arg, self.src.rng(k)) for k in extras]})

    # -- expressions -------------------------------------------------------

    @staticmethod
    def dotted(node: ast.expr) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = _Checker.dotted(node.value)
            return f"{base}.{node.attr}" if base is not None else None
        return None

    def returns_module_value(self, node: ast.expr) -> bool:
        if isinstance(node, ast.Call):
            d = self.dotted(node.func)
            if d is not None and self.reg.module_call_allowed(d):
                return True
            return isinstance(node.func, ast.Attribute) and self.returns_module_value(node.func.value)
        if isinstance(node, ast.Attribute):
            return self.returns_module_value(node.value)
        return False

    def load(self, name: str, st: _State) -> None:
        self.loads.setdefault(st.in_def, set()).add(name)

    def expr(self, e: ast.expr, st: _State) -> None:
        unsupported = None
        if isinstance(e, ast.Constant):
            if isinstance(e.value, bytes):
                unsupported = "A bytes literal"
            elif isinstance(e.value, complex):
                unsupported = "A complex number"
            elif e.value is Ellipsis:
                unsupported = "`...`"
        elif isinstance(e, ast.JoinedStr):
            for v in e.values:
                if isinstance(v, ast.FormattedValue):
                    self.expr(v.value, st)
                    if v.format_spec is not None:
                        self.expr(v.format_spec, st)
        elif isinstance(e, ast.FormattedValue):
            self.expr(e.value, st)
        elif isinstance(e, ast.Name):
            self.load(e.id, st)
            if not (e.id in self.visible(st) or e.id in self.reg.modules or e.id in self.reg.functions):
                self.add("undefined-name", self.src.rng(e), name=e.id)
        elif isinstance(e, (ast.List, ast.Tuple)):
            for x in e.elts:
                if isinstance(x, ast.Starred):
                    self.add("unsupported-expression", self.src.rng(x), construct="`*` unpacking", hint="")
                else:
                    self.expr(x, st)
        elif isinstance(e, ast.Dict):
            for k, v in zip(e.keys, e.values):
                if k is None:
                    self.add("unsupported-expression", self.src.rng(v), construct="`**` unpacking", hint="")
                    continue
                self.expr(k, st)
                self.expr(v, st)
        elif isinstance(e, ast.Set):
            unsupported = "A set"
        elif isinstance(e, ast.BinOp):
            if type(e.op) in _BAD_BINOPS:
                unsupported = f"The `{_BAD_BINOPS[type(e.op)]}` operator"
            else:
                self.expr(e.left, st)
                self.expr(e.right, st)
        elif isinstance(e, ast.UnaryOp):
            if isinstance(e.op, ast.Invert):
                unsupported = "The `~` operator"
            else:
                self.expr(e.operand, st)
        elif isinstance(e, ast.BoolOp):
            for v in e.values:
                self.expr(v, st)
        elif isinstance(e, ast.Compare):
            self.expr(e.left, st)
            for c in e.comparators:
                self.expr(c, st)
        elif isinstance(e, ast.IfExp):
            self.expr(e.test, st)
            self.expr(e.body, st)
            self.expr(e.orelse, st)
        elif isinstance(e, ast.Subscript):
            self.expr(e.value, st)
            self.slice_expr(e.slice, st)
        elif isinstance(e, ast.Call):
            self.call_expr(e, st)
        elif isinstance(e, ast.Attribute):
            d = self.dotted(e)
            root = d.split(".")[0] if d else None
            if d is not None and root in self.reg.modules and self.reg.module_attr_allowed(d):
                pass
            elif d is None and self.returns_module_value(e.value):
                self.expr(e.value, st)
            else:
                unsupported = "Attribute access"
                self.add("unsupported-expression", self.src.rng(e), construct=unsupported, hint=": only on random, math, datetime and the values they return")
                return
        elif isinstance(e, ast.Lambda):
            unsupported = "`lambda`"
        elif isinstance(e, ast.NamedExpr):
            unsupported = "`:=`"
        elif isinstance(e, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            unsupported = "A comprehension"
        elif isinstance(e, ast.Await):
            unsupported = "`await`"
        elif isinstance(e, (ast.Yield, ast.YieldFrom)):
            unsupported = "`yield`"
        elif isinstance(e, ast.Starred):
            unsupported = "`*` unpacking"
        else:
            unsupported = f"`{type(e).__name__}`"
        if unsupported is not None:
            self.add("unsupported-expression", self.src.rng(e), construct=unsupported, hint="")

    def slice_expr(self, s: ast.AST, st: _State) -> None:
        if isinstance(s, ast.Slice):
            for part in (s.lower, s.upper, s.step):
                if part is not None:
                    self.expr(part, st)
        elif isinstance(s, ast.Tuple):
            for x in s.elts:
                self.slice_expr(x, st)
        elif hasattr(ast, "Index") and isinstance(s, getattr(ast, "Index")):  # Python 3.8
            self.expr(s.value, st)  # type: ignore[attr-defined]
        else:
            self.expr(s, st)

    def call_args(self, e: ast.Call, st: _State) -> None:
        for a in e.args:
            if isinstance(a, ast.Starred):
                self.add("unsupported-expression", self.src.rng(a), construct="`*` unpacking", hint="")
            else:
                self.expr(a, st)
        for k in e.keywords:
            if k.arg is None:
                self.add("unsupported-expression", self.src.rng(k.value), construct="`**` unpacking", hint="")
            else:
                self.expr(k.value, st)

    def call_expr(self, e: ast.Call, st: _State) -> None:
        f = e.func
        if isinstance(f, ast.Name):
            n = f.id
            if n in self.reg.functions:
                self.call_args(e, st)
            elif n == "parameter":
                self.add("parameter-not-assigned", self.src.rng(e))
            elif self.reg.kind(n) in ("statement", "context") or n in self.defs:
                self.add("statement-as-value", self.src.rng(e), name=n)
            else:
                self.add("unknown-function", self.src.rng(e), name=n)
            return
        if isinstance(f, ast.Attribute):
            d = self.dotted(f)
            if d is not None:
                root = d.split(".")[0]
                if root in self.reg.modules:
                    if self.reg.module_call_allowed(d):
                        self.call_args(e, st)
                    else:
                        self.add("unknown-function", self.src.rng(e), name=d)
                    return
                if d.count(".") == 1 and root not in self.visible(st) and screenplan_name_problem(root, "workspace") is None:
                    self.add("statement-as-value", self.src.rng(e), name=d)
                    return
                self.add("unknown-function", self.src.rng(e), name=d)
                return
            if self.returns_module_value(f.value):
                self.expr(f.value, st)
                self.call_args(e, st)
                return
            self.add("unknown-function", self.src.rng(e), name=f.attr)
            return
        self.add("unknown-function", self.src.rng(e), name="…")

    # -- whole-event checks ------------------------------------------------

    def check_recursion(self) -> None:
        graph: Dict[str, List[str]] = {}
        for frm, to, _, _ in self.edges:
            if frm is not None:
                graph.setdefault(frm, []).append(to)

        def path(start: str, goal: str) -> Optional[List[str]]:
            seen = set()
            stack = [(start, [start])]
            while stack:
                node, p = stack.pop(0)
                if node == goal:
                    return p
                if node in seen:
                    continue
                seen.add(node)
                for nxt in graph.get(node, []):
                    stack.append((nxt, p + [nxt]))
            return None

        for frm, to, r, _ in self.edges:
            if frm is None or to not in self.defs:
                continue
            p = path(to, frm)
            if p is not None:
                chain = [frm] + p
                via = "" if to == frm else " through " + ", ".join(f"`{x}()`" for x in chain[1:-1])
                self.add("recursive-sequence", r, name=frm, via=via)

    def total_calls(self) -> int:
        memo: Dict[str, Optional[int]] = {}

        def of(scope: Optional[str], visiting: Tuple[str, ...]) -> int:
            if scope is not None:
                if scope in memo and memo[scope] is not None:
                    return memo[scope]  # type: ignore[return-value]
                if scope in visiting:
                    return 0
            n = self.counts.get(scope, 0)
            for frm, to, _, mult in self.edges:
                if frm == scope and to in self.defs:
                    n += mult * of(to, visiting + ((scope,) if scope else ()))
            if scope is not None:
                memo[scope] = n
            return n

        return of(None, ())

    def context_checks(self, ctx: Dict[str, Any]) -> None:
        workspaces = ctx.get("workspaces")
        hosts = ctx.get("hosts")
        mappings = ctx.get("hostMappings")
        mapping_names = set(mappings.keys() if isinstance(mappings, dict) else (mappings or []))
        saved = ctx.get("controlBoardEvents")

        if isinstance(workspaces, dict):
            lowered = {w.lower(): w for w in workspaces}
            for name, r, kind, scope in self.sites:
                if name.lower() in lowered:
                    self.add("name-hides-workspace", r, name=name)
        for c in self.script_calls:
            call = f"{c['ws']}.{c['script']}"
            if isinstance(workspaces, dict):
                ws = workspaces.get(c["ws"])
                if ws is None:
                    self.add("unknown-workspace", c["range"], name=c["ws"])
                    continue
                scripts = ws.get("scripts")
                if isinstance(scripts, dict):
                    info = scripts.get(c["script"])
                    if info is None:
                        self.add("script-not-found", c["range"], call=call)
                        continue
                    deployed = info.get("hosts")
                    if isinstance(deployed, list) and isinstance(c["hosts"], list) and isinstance(hosts, dict):
                        for h in c["hosts"]:
                            if h in hosts and h not in deployed:
                                self.add("script-not-deployed", c["range"], call=call, host=h)
                    inputs = info.get("inputs")
                    if isinstance(inputs, list):
                        declared = [i["name"] if isinstance(i, dict) else i for i in inputs]
                        for k in c["keywords"]:
                            if k not in declared:
                                self.add("unknown-script-input", c["range"], call=call, keyword=k)
                        for i in inputs:
                            if isinstance(i, dict) and i.get("required") and i["name"] not in c["keywords"]:
                                self.add("missing-script-input", c["range"], call=call, input=i["name"])
        if isinstance(hosts, dict):
            for h, r in self.host_literals:
                if h not in hosts and h not in mapping_names:
                    self.add("unknown-host", r, host=h)
            for d in self.devices:
                targets = d["hosts"]
                if isinstance(targets, list):
                    known = [h for h in targets if h in hosts]
                    if len(known) != len(targets):
                        continue
                    attached = set()
                    for h in known:
                        attached.update(hosts[h].get("devices", []) or [])
                    where = ", ".join(known)
                elif targets is None:
                    attached = set()
                    for info in hosts.values():
                        attached.update(info.get("devices", []) or [])
                    where = "any host"
                else:
                    continue
                if d["device"] not in attached:
                    self.add("device-not-attached", d["range"], device=d["device"], where=where)
        if isinstance(saved, dict):
            for ev in self.run_events:
                info = saved.get(ev["path"])
                if info is None:
                    self.add("unknown-saved-event", ev["range"], path=ev["path"])
                    continue
                params = info.get("parameters")
                if isinstance(params, list):
                    for k, r in ev["keywords"]:
                        if k not in params:
                            self.add("unknown-event-parameter", r, path=ev["path"], keyword=k)
        if self.unwrapped:
            self.add("no-target-host", self.unwrapped[0])
        reported = set()
        for name, r, kind, scope in self.sites:
            if kind != "variable" or (scope, name) in reported:
                continue
            reported.add((scope, name))
            if scope is None:
                used = any(name in names for names in self.loads.values())
            else:
                used = name in self.loads.get(scope, set())
            if not used:
                self.add("unused-variable", r, name=name)


# ---------------------------------------------------------------------------
# outline


class _Outliner:
    def __init__(self, src: _Source, tree: ast.Module):
        self.src = src
        self.reg = _registry()
        self.defs = {s.name: s for s in tree.body if isinstance(s, ast.FunctionDef)}

    def args_src(self, call: ast.Call) -> str:
        parts: List[ast.AST] = list(call.args) + list(call.keywords)
        if not parts:
            return ""
        ranges = [self.src.rng(p) for p in parts]
        start = min((r[0], r[1]) for r in ranges)
        end = max((r[2], r[3]) for r in ranges)
        return self.src.slice((start[0], start[1], end[0], end[1]))

    def build(self, stmts: List[ast.stmt]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for s in stmts:
            out.extend(self.step(s))
        return out

    def step(self, s: ast.stmt) -> List[Dict[str, Any]]:
        line = s.lineno
        if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call):
            v = s.value
            f = v.func
            if isinstance(f, ast.Name):
                if f.id in self.defs:
                    return [{"type": "sequence", "kind": "def", "name": f.id, "line": line, "args": self.args_src(v), "steps": self.build(self.defs[f.id].body)}]
                return [{"type": "command", "line": line, "name": f.id, "args": self.args_src(v)}]
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                return [{
                    "type": "script", "line": line, "call": f"{f.value.id}.{f.attr}", "workspace": f.value.id, "script": f.attr,
                    "inputs": [k.arg for k in v.keywords if k.arg is not None],
                }]
            return []
        if isinstance(s, ast.Assign):
            return [{"type": "variable", "line": line, "name": s.targets[0].id, "value": self.src.src(s.value)}]  # type: ignore[attr-defined]
        if isinstance(s, ast.If):
            branches = []
            node: Optional[ast.If] = s
            label = "if"
            while node is not None:
                cond = self.src.src(node.test)
                branches.append({"type": "sequence", "kind": "branch", "name": f"{label} {cond}", "line": node.lineno, "steps": self.build(node.body)})
                orelse = node.orelse
                if len(orelse) == 1 and isinstance(orelse[0], ast.If) and self.is_elif(orelse[0]):
                    node = orelse[0]
                    label = "elif"
                    continue
                if orelse:
                    branches.append({"type": "sequence", "kind": "branch", "name": "else", "line": orelse[0].lineno, "steps": self.build(orelse)})
                node = None
            return [{"type": "command", "line": line, "name": "if", "condition": self.src.src(s.test), "branches": branches}]
        if isinstance(s, ast.For):
            target = s.target.id  # type: ignore[attr-defined]
            values: List[str]
            it = s.iter
            if isinstance(it, ast.Call):
                nums = [self._int(a) for a in it.args]
                values = [str(i) for i in range(*nums)]
            else:
                values = [self.src.src(e) for e in it.elts]  # type: ignore[attr-defined]
            iterations = []
            for value in values:
                iterations.append({
                    "type": "sequence", "kind": "iteration", "name": f"{target} = {value}", "line": line,
                    "steps": [{"type": "variable", "line": line, "name": target, "value": value}] + self.build(s.body),
                })
            return [{"type": "sequence", "kind": "for", "name": f"for {target} in {self.src.src(it)}", "line": line, "steps": iterations}]
        if isinstance(s, ast.With):
            first = self.src.rng(s.items[0].context_expr)
            last = self.src.rng(s.items[-1].context_expr)
            context = []
            parallel = False
            for item in s.items:
                call = item.context_expr
                context.append({"name": call.func.id, "args": self.args_src(call)})  # type: ignore[attr-defined]
                if call.func.id == "parallel":  # type: ignore[attr-defined]
                    parallel = True
            step = {
                "type": "sequence", "kind": "with", "name": self.src.slice((first[0], first[1], last[2], last[3])), "line": line,
                "context": context, "steps": self.build(s.body),
            }
            if parallel:
                step["parallel"] = True
            return [step]
        if isinstance(s, ast.Try):
            return self.build(s.body) + [{
                "type": "sequence", "kind": "finally", "name": "onDestroy", "line": s.finalbody[0].lineno, "steps": self.build(s.finalbody),
            }]
        return []

    def is_elif(self, node: ast.If) -> bool:
        line = self.src.lines[node.lineno - 1]
        c = self.src.col(node.lineno, node.col_offset)
        return line[c - 1 : c + 3] == "elif"

    @staticmethod
    def _int(node: ast.expr) -> int:
        if isinstance(node, ast.UnaryOp):
            v = node.operand.value  # type: ignore[attr-defined]
            return -v if isinstance(node.op, ast.USub) else v
        return node.value  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# entry points


def _sorted(diags: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for d in sorted(diags, key=lambda d: (d["line"], d["column"], d["endLine"], d["endColumn"], d["code"], d["message"])):
        key = (d["code"], d["line"], d["column"], d["endLine"], d["endColumn"], d["message"])
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def _result(grammar: int, diags: List[Dict[str, Any]], unchecked: List[Dict[str, Any]], outline_steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    reg = _registry()
    errors = _sorted(d for d in diags if reg.templates[d["code"]]["severity"] == "error")
    warnings = _sorted(d for d in diags if reg.templates[d["code"]]["severity"] == "warning")
    return {"ok": not errors, "grammar": grammar, "errors": errors, "warnings": warnings, "unchecked": unchecked, "outline": outline_steps}


_TODO_RE = re.compile(r"^(\s*)# TODO\(grammar 1\)")


def _grammar1_todos(src: _Source) -> List[Dict[str, Any]]:
    """A ``# TODO(grammar 1):`` comment, left by the grammar 2 migration where
    it couldn't translate a line, is an error, so the event can't be saved
    until someone writes that part in grammar 2."""
    message = _registry().templates["grammar-1-todo"]["message"]
    out = []
    for i, line in enumerate(src.lines):
        m = _TODO_RE.match(line)
        if m:
            out.append({
                "code": "grammar-1-todo", "line": i + 1, "column": len(m.group(1)) + 1,
                "endLine": i + 1, "endColumn": len(line.rstrip()) + 1, "message": message,
            })
    return out


def check(text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The grammar checker: the grammar level always, the context level when
    ``context`` is given. Returns the event-check-result shape."""
    reg = _registry()
    text = _normalize(text)
    src = _Source(text)
    state, idx = _header_state(src.lines)
    unchecked = [dict(u) for u in (context or {}).get("unchecked", []) or []] if context is not None else []
    if state == "none" and not _looks_grammar2(src.lines):
        line = (idx if idx is not None else 0) + 1
        end = len(src.lines[line - 1]) + 1 if src.lines else 1
        d = {
            "code": "grammar-1-not-accepted", "line": line, "column": 1, "endLine": line, "endColumn": end,
            "message": reg.templates["grammar-1-not-accepted"]["message"],
        }
        return _result(1, [d], unchecked, [])
    diags: List[Dict[str, Any]] = []
    if state == "malformed":
        line = idx + 1  # type: ignore[operator]
        diags.append({
            "code": "missing-header", "line": line, "column": 1, "endLine": line, "endColumn": len(src.lines[line - 1]) + 1,
            "message": reg.templates["missing-header"]["message"], "fix": {"replace": HEADER, "label": "fix the header"},
        })
    elif state == "none":
        diags.append({
            "code": "missing-header", "line": 1, "column": 1, "endLine": 1, "endColumn": 1,
            "message": reg.templates["missing-header"]["message"], "fix": {"replace": HEADER + "\n", "label": "add the header"},
        })
    diags.extend(_grammar1_todos(src))
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as error:
        line = getattr(error, "lineno", None) or 1
        col = getattr(error, "offset", None) or 1
        detail = getattr(error, "msg", None) or str(error)
        diags.append({
            "code": "syntax-error", "line": line, "column": col, "endLine": line, "endColumn": col + 1,
            "message": reg.templates["syntax-error"]["message"].format(detail=detail),
        })
        return _result(2, diags, unchecked, [])
    checker = _Checker(src, tree)
    checker.run()
    grammar_errors = [d for d in checker.diags if reg.templates[d["code"]]["severity"] == "error"]
    if context is not None:
        checker.context_checks(context)
    diags.extend(checker.diags)
    steps = _Outliner(src, tree).build(tree.body) if not grammar_errors else []
    return _result(2, diags, unchecked, steps)


def validate(text: str) -> List[Dict[str, Any]]:
    """The grammar level's diagnostics (errors), as a list."""
    r = check(text)
    return r["errors"] + r["warnings"]


def outline(text: str) -> List[Dict[str, Any]]:
    """What the event will run, as structured steps; empty when it has grammar errors."""
    return check(text)["outline"]
