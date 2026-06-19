import json
from datetime import UTC, datetime

import pytest
from conftest import FakeSampling, FakeStorage

from truman_director.engine import apply_inject_event, tick
from truman_director.errors import TickBudgetExceededError
from truman_director.scenarios import build


def _fresh_world():
    return build("cafe_town", datetime(2026, 6, 19, 8, 0, tzinfo=UTC))


async def test_tick_advances_and_records_events():
    world = _fresh_world()
    sampling = FakeSampling(
        events=[
            {"agent_id": "alice", "action": "move", "target": "loc_cafe", "reason": "open shop"},
        ]
    )
    storage = FakeStorage()
    results = await tick(world, sampling, storage, n=2)
    assert len(results) == 2
    assert world.current_tick == 2
    # each tick recorded one event
    assert len(world.events) == 2
    # world persisted each tick
    assert storage.data  # something saved


async def test_inject_event_fires_next_tick():
    world = _fresh_world()
    sampling = FakeSampling(events=[])
    storage = FakeStorage()
    queued = apply_inject_event(
        world, {"agent_id": "truman", "action": "talk", "target": "alice", "reason": "say hi"}
    )
    assert queued["effective_tick"] == world.current_tick + 1
    results = await tick(world, sampling, storage, n=1)
    # injected event appears alongside model events
    flat = results[0]["events"]
    assert any(e.get("reason") == "say hi" for e in flat)


async def test_director_world_change_enters_shared_context():
    """A director's world_change injection (e.g. 'a storm breaks out') is recorded as a
    world event that every resident shares in the next snapshot — so the world-simulator
    can react to it instead of ignoring the director."""
    world = _fresh_world()
    sampling = FakeSampling(events=[])
    storage = FakeStorage()
    apply_inject_event(world, {"reason": "a sudden storm breaks out"})
    await tick(world, sampling, storage, n=1)
    snap = world.snapshot()
    world_changes = [e for e in snap["events"] if e["event_type"] == "world_change"]
    assert any("storm" in e["description"].lower() for e in world_changes)
    # high importance — the director made it happen
    assert all(e["importance"] >= 0.9 for e in world_changes)


async def test_director_injection_visible_to_model_same_tick():
    """The director's injection must be inside the snapshot the model receives THIS
    tick — otherwise residents react one tick too late. Guards the tick ordering
    (drain+apply+record injections BEFORE snapshot, not after decide)."""
    world = _fresh_world()
    sampling = FakeSampling(events=[])
    storage = FakeStorage()
    apply_inject_event(world, {"reason": "a sudden storm breaks out"})
    await tick(world, sampling, storage, n=1)
    assert len(sampling.calls) == 1
    world_view = json.loads(sampling.calls[0]["messages"][0]["content"]["text"])
    world_changes = [e for e in world_view["events"] if e["event_type"] == "world_change"]
    assert any("storm" in e["description"].lower() for e in world_changes)


def test_system_prompt_loaded_from_yaml():
    """SYSTEM_PROMPT is loaded from prompts.yaml (not hardcoded) and carries the
    directives that make the simulation + director injections work."""
    from truman_director.engine import SYSTEM_PROMPT

    assert "world-simulator" in SYSTEM_PROMPT
    assert "world_change" in SYSTEM_PROMPT
    assert len(SYSTEM_PROMPT) > 500


async def test_tick_rejects_over_budget():
    """Asking for more ticks than MAX_TICKS_PER_INVOKE fails loud BEFORE any
    sampling or persist — never a half-applied world that saved the first few."""
    from truman_director.engine import MAX_TICKS_PER_INVOKE

    world = _fresh_world()
    sampling = FakeSampling(events=[])
    storage = FakeStorage()
    with pytest.raises(TickBudgetExceededError):
        await tick(world, sampling, storage, n=MAX_TICKS_PER_INVOKE + 1)
    # nothing consumed, nothing persisted — zero side effects
    assert sampling.calls == []
    assert not storage.data
