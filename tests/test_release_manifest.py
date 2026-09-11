"""Prevent publishing App metadata as the tool's protocol manifest."""

import json
from pathlib import Path

from truman_director.plugin import MANIFEST


def test_published_protocol_manifest_matches_describe():
    root = Path(__file__).resolve().parents[1]
    declaration = json.loads((root / "executa.json").read_text(encoding="utf-8"))
    assert declaration["manifest_file"] == "executa-manifest.json"
    protocol = json.loads((root / declaration["manifest_file"]).read_text(encoding="utf-8"))
    assert protocol == MANIFEST
    assert protocol["version"] == declaration["version"]
    assert "schema" not in protocol  # schema:2 belongs to the separate App manifest
