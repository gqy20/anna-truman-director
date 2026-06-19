from datetime import UTC, datetime

from conftest import FakeSampling, FakeStorage

from truman_director.engine import apply_inject_event, tick
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
