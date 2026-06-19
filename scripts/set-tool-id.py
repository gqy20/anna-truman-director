#!/usr/bin/env python3
"""Sync a minted tool_id across the three files that carry it.

Usage:
    python scripts/set-tool-id.py apply --tool tool-<yourhandle>-truman-director-<hash>

After minting at https://anna.partners/executa, run this so pyproject.toml
(both the package ``name`` and the console-script entry) plus executa.json and
bundle/app.js all agree on the real tool_id. The plugin itself carries no id:
it is the *callee* — the host spawns it by the console-script name, and the
id is needed only on the caller side (bundle) and the declaration side
(pyproject / executa.json). ``anna-app apps publish`` runs this same sync
automatically; this script is for manual sync / local dev. Idempotent — safe
to re-run after a re-mint.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (relative_path, [(regex, replacement_with_{tool_id} placeholder)])
FILES: dict[str, list[tuple[str, str]]] = {
    "pyproject.toml": [
        (r'^name = "tool-[^"]*"$', 'name = "{tool_id}"'),
        (
            r'^"tool-[^"]*" = "truman_director\.plugin:main"$',
            '"{tool_id}" = "truman_director.plugin:main"',
        ),
    ],
    "executa.json": [
        (r'"tool_id":\s*"tool-[^"]*"', '"tool_id": "{tool_id}"'),
    ],
    "bundle/app.js": [
        # The only `tool-...` string literal in the bundle (the dev fallback
        # in EXECUTA_TOOL_ID). Match any tool_id, not the hardcoded DEV literal,
        # so re-running after a re-mint still works.
        (r'"tool-[A-Za-z0-9_-]+"', '"{tool_id}"'),
    ],
}

TOOL_ID_RE = re.compile(r"tool-[A-Za-z0-9_-]+")


def apply(tool_id: str) -> None:
    for rel, patterns in FILES.items():
        path = ROOT / rel
        if not path.exists():
            print(f"skip (missing): {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        for pat, repl in patterns:
            text = re.sub(pat, repl.format(tool_id=tool_id), text, flags=re.M)
        path.write_text(text, encoding="utf-8")
        print(f"updated: {rel}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    apply_p = sub.add_parser("apply", help="rewrite the tool_id in all files")
    apply_p.add_argument("--tool", required=True, help="the minted tool_id")
    args = parser.parse_args()

    if args.cmd == "apply":
        if not TOOL_ID_RE.fullmatch(args.tool):
            raise SystemExit(f"not a valid tool_id: {args.tool!r}")
        apply(args.tool)


if __name__ == "__main__":
    main()
