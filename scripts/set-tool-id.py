#!/usr/bin/env python3
"""Sync a minted tool_id across the four files that carry it.

Usage:
    python scripts/set-tool-id.py apply --tool tool-<yourhandle>-truman-director-<hash>

After minting at https://anna.partners/executa, run this so pyproject.toml,
executa.json, plugin.py and bundle/app.js all agree on the real tool_id.
`anna-app apps publish` invokes the same logic automatically; this script is
for manual sync / local dev.
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
    "src/truman_director/plugin.py": [
        (r"tool_id:\s*tool-[A-Za-z0-9_-]+", "tool_id: {tool_id}"),
    ],
    "bundle/app.js": [
        (r'"tool-DEV-truman-director-xxxxxxxx"', '"{tool_id}"'),
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
