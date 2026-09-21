"""A failed tick must remain retryable without losing time or queued input."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from conftest import FakeSampling, FakeStorage

from truman_director import engine, plugin
from truman_director.scenarios import build
from truman_director.storage import KEY, save


@pytest.mark.parametrize("phase", ["decide", "narrate", "save", "cancel"])
async def test_failed_midnight_tick_preserves_world_and_retries(monkeypatch, phase):
    world = build("cafe_town", datetime(2026, 9, 21, tzinfo=UTC))
    world.world_time = "23:55"
    engine.apply_inject_event(
        world,
        {"agent_id": "alice", "action": "move", "target": "loc_cafe", "reason": "open shop"},
    )
    # More history than snapshot() preserves: rollback must not truncate memory.
    for i in range(25):
        world.record_event({"action": "world_change", "reason": f"past event {i}"})
    storage = FakeStorage()
    await save(storage, world.snapshot())
    before_world, before_storage = deepcopy(world), deepcopy(storage.data)

    async def fail(*args, **kwargs):
        # Even while sampling / saving is awaited, no uncommitted state leaks.
        assert world == before_world
        if phase == "cancel":
            raise asyncio.CancelledError()
        raise RuntimeError("injected failure")

    with monkeypatch.context() as m:
        if phase == "save":
            m.setattr(storage, "set", fail)
        else:
            m.setattr(engine, "decide" if phase == "cancel" else phase, fail)
        error = asyncio.CancelledError if phase == "cancel" else RuntimeError
        with pytest.raises(error):
            await engine.tick(world, FakeSampling(), storage, lang="en")
    assert world == before_world
    assert storage.data == before_storage

    writes = []
    original_set = storage.set

    async def capture_set(key, value, **kwargs):
        writes.append(deepcopy(value))
        return await original_set(key, value, **kwargs)

    monkeypatch.setattr(storage, "set", capture_set)
    result = await engine.tick(world, FakeSampling(), storage, lang="en")
    assert world.current_tick == 1
    assert world.world_time == "00:00"
    assert world.day == 2
    assert world.lang == "en"
    assert not world._pending_injections
    assert world.agents["alice"].current_location_id == "loc_cafe"
    assert len(world.events) == 26
    assert len(world.stories) == 1
    assert sum("day_story" in item for item in result) == 1
    assert len(writes) == 1
    assert writes[0] == storage.data[KEY]["value"] == world.snapshot()
    assert len(writes[0]["stories"]) == 1


async def test_two_failed_plugin_ticks_then_retry_do_not_skip_numbers(monkeypatch):
    world = build("cafe_town", datetime(2026, 9, 21, tzinfo=UTC))
    storage = FakeStorage()
    await save(storage, world.snapshot())
    monkeypatch.setattr(plugin, "_world", world)
    monkeypatch.setattr(plugin, "_storage", storage)
    monkeypatch.setattr(plugin, "_sampling", FakeSampling())
    before = deepcopy(world)

    async def fail(*args, **kwargs):
        raise RuntimeError("sampling HTTP 502")

    with monkeypatch.context() as m:
        m.setattr(engine, "decide", fail)
        for _ in range(2):
            with pytest.raises(RuntimeError, match="sampling HTTP 502"):
                await plugin._tool_world(action="tick", lang="en")
            assert world == before
            assert storage.data[KEY]["value"]["current_tick"] == 0

    result = await plugin._tool_world(action="tick", lang="en")
    assert result["results"][0]["tick"] == 1
    assert world.lang == "en"
    # A fresh plugin process must resume the committed tick and language.
    monkeypatch.setattr(plugin, "_world", None)
    restored = await plugin._require_world()
    assert restored.snapshot() == world.snapshot()


async def test_multi_tick_failure_keeps_earlier_committed_tick(monkeypatch):
    world = build("cafe_town", datetime(2026, 9, 21, tzinfo=UTC))
    storage = FakeStorage()
    original_decide = engine.decide
    calls = 0

    async def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second tick failed")
        return await original_decide(*args, **kwargs)

    with monkeypatch.context() as m:
        m.setattr(engine, "decide", fail_second)
        with pytest.raises(RuntimeError, match="second tick failed"):
            await engine.tick(world, FakeSampling(), storage, n=3)
    assert world.current_tick == 1
    assert storage.data[KEY]["value"] == world.snapshot()
    await engine.tick(world, FakeSampling(), storage)
    assert world.current_tick == 2
