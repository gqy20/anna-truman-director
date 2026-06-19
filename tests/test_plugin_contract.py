"""Protocol contract: JSON-RPC over stdio for the host-initiated methods.

We only exercise describe / health / initialize here — they need no host.
init / tick route through the reverse-RPC clients (StorageClient / SamplingClient),
which require a live host on stdin; their logic is covered by the unit tests
with async fakes instead.
"""

from __future__ import annotations

import json
import subprocess
import sys


def _rpc(*requests: dict) -> list[dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "truman_director.plugin"],
        input="\n".join(json.dumps(r) for r in requests) + "\n",
        capture_output=True,
        text=True,
        timeout=15,
    )
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def test_describe_returns_world_tool():
    resp = _rpc({"jsonrpc": "2.0", "id": 1, "method": "describe"})[0]
    manifest = resp["result"]
    assert manifest["display_name"] == "Truman Director"
    assert manifest["tools"][0]["name"] == "world"
    params = {p["name"]: p for p in manifest["tools"][0]["parameters"]}
    assert params["action"]["required"] is True


def test_health_reports_ok():
    resp = _rpc({"jsonrpc": "2.0", "id": 1, "method": "health"})[0]
    assert resp["result"]["status"] == "ok"


def test_initialize_negotiates_v2_with_capabilities():
    resp = _rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize"})[0]
    result = resp["result"]
    assert result["protocolVersion"] == "2.0"
    assert result["capabilities"]["storage"]["kv"] is True
    assert result["capabilities"]["sampling"]["enabled"] is True


def test_unknown_method_returns_error():
    resp = _rpc({"jsonrpc": "2.0", "id": 9, "method": "bogus"})[0]
    assert resp["error"]["code"] == -32601
