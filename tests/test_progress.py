"""executa/progress notifications (M1.6, DESIGN §6.3).

emit_progress is best-effort and correlated: frames only flow when an
invoke_id is bound (bind_invoke), carry that id in params.context, and are
valid JSON-RPC notifications — never requests, never on stdout garbage.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from conftest import FakeSampling, FakeStorage
from executa_sdk import bind_invoke

from truman_director.engine import tick
from truman_director.scenarios import build


def _fresh_world():
    return build("cafe_town", datetime(2026, 8, 15, tzinfo=UTC))


async def test_progress_emits_correlated_frames_per_tick(capsys):
    world = _fresh_world()
    with bind_invoke({"context": {"invoke_id": "inv-test-1"}}):
        await tick(world, FakeSampling(), FakeStorage(), n=2)
    frames = [json.loads(ln) for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    prog = [f for f in frames if f.get("method") == "executa/progress"]
    assert len(prog) == 2  # one tool_update per tick of the multi-tick run
    for f in prog:
        assert f["params"]["context"]["invoke_id"] == "inv-test-1"
        assert f["params"]["type"] == "tool_update"
        assert f["params"]["data"]["kind"] == "tick"
        assert "id" not in f  # notification, not a request


async def test_progress_silent_without_bound_invoke(capsys):
    world = _fresh_world()
    await tick(world, FakeSampling(), FakeStorage(), n=2)
    assert "executa/progress" not in capsys.readouterr().out


async def test_single_tick_run_emits_no_progress(capsys):
    world = _fresh_world()
    with bind_invoke({"context": {"invoke_id": "inv-single"}}):
        await tick(world, FakeSampling(), FakeStorage(), n=1)
    assert "executa/progress" not in capsys.readouterr().out
