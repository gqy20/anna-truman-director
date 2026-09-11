"""Export the plugin's describe result; never use the App manifest as a tool manifest."""

import argparse
import json
from pathlib import Path

from truman_director.plugin import MANIFEST


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    declaration = json.loads((root / "executa.json").read_text(encoding="utf-8"))
    if declaration["version"] != MANIFEST["version"]:
        raise SystemExit("executa.json and plugin versions differ")
    target = root / declaration["manifest_file"]
    if target != root / "executa-manifest.json":
        raise SystemExit("Expected dedicated executa-manifest.json, not the App manifest")
    expected = json.dumps(MANIFEST, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != expected:
            raise SystemExit("Stale tool manifest: run scripts/export_executa_manifest.py")
        print("Tool protocol manifest matches describe and version")
    else:
        target.write_text(expected, encoding="utf-8")
        print(f"Exported {target.name} ({MANIFEST['version']})")


if __name__ == "__main__":
    main()
