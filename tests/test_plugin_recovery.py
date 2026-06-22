"""Recovery path: a plugin restart must resume the world from the APS KV
snapshot rather than forcing the user to re-init.

``plugin._world`` is module-level state that dies with the Executa process — an
Agent restart / crash / redeploy reboots it to ``None``. ``_tool_world`` must
transparently restore it from storage on the next ``tick`` / ``inject_event``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from conftest import FakeSampling, FakeStorage

import truman_director.plugin as plugin
from truman_director.errors import WorldNotInitializedError
from truman_director.scenarios import build


def _seed_storage_with_snapshot(storage: FakeStorage) -> dict:
    """Run one tick into a fresh world, persist it to fake storage, return snapshot."""
    world = build("cafe_town", datetime(2026, 6, 19, 8, 0, tzinfo=UTC))
    snapshot = world.snapshot()
    storage.data["truman:run:world"] = {"value": snapshot, "etag": "etag-1"}
    return snapshot


def _install_module_storage(storage: FakeStorage) -> None:
    """Point the plugin's module-level _storage at the fake (mimics what real
    imports bind: a StorageClient writing to APS KV)."""
    plugin._storage = storage  # type: ignore[attr-defined]


def _reset_module_world() -> None:
    """Simulate an Executa process restart: module-level _world goes to None."""
    plugin._world = None  # type: ignore[attr-defined]


async def test_tick_restores_world_from_storage_after_restart():
    """The headline fix: tick on a fresh process finds no _world, loads the
    snapshot from storage, and resumes — no re-init needed."""
    storage = FakeStorage()
    _install_module_storage(storage)
    _seed_storage_with_snapshot(storage)

    _reset_module_world()
    plugin._sampling = FakeSampling(events=[])  # type: ignore[attr-defined]

    # Despite _world being None, tick must succeed by restoring from storage.
    result = await plugin._tool_world(action="tick", n=1)
    assert plugin._world is not None
    assert result["results"][0]["tick"] == 1
    assert plugin._world.current_tick == 1


async def test_tick_raises_when_no_world_and_no_snapshot():
    """The only genuinely-uninitialized case: nothing in memory AND nothing in
    storage. Must fail loud (red line 4), not silently no-op."""
    storage = FakeStorage()
    _install_module_storage(storage)
    _reset_module_world()
    plugin._sampling = FakeSampling(events=[])  # type: ignore[attr-defined]

    with pytest.raises(WorldNotInitializedError):
        await plugin._tool_world(action="tick", n=1)


async def test_inject_event_restores_world_from_storage_after_restart():
    """inject_event too must self-heal — otherwise a restart kills the director
    UI until the user notices and re-inits."""
    storage = FakeStorage()
    _install_module_storage(storage)
    _seed_storage_with_snapshot(storage)

    _reset_module_world()

    ack = await plugin._tool_world(
        action="inject_event",
        event={"reason": "a storm breaks out"},
    )
    assert plugin._world is not None
    assert ack["effective_tick"] == 1
