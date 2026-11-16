"""python -m screenplan_contracts.event_grammar check <file> [--context <json file>]

Prints the check result as JSON (event-check-result.schema.json) and exits 1
when the event has errors. `-` reads the event from stdin. Without --context
only the grammar level runs."""
from __future__ import annotations

import argparse
import json
import sys

from .checker import check


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m screenplan_contracts.event_grammar")
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check", help="check an event's text")
    c.add_argument("file", help="the event's text, or - for stdin")
    c.add_argument("--context", help="a JSON file with the context: workspaces, hosts, hostMappings, controlBoardEvents, unchecked")
    args = parser.parse_args(argv)
    text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
    context = None
    if args.context:
        with open(args.context, encoding="utf-8") as f:
            context = json.load(f)
    result = check(text, context)
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
