"""Production storage boundary: frontend reads the plugin's committed snapshot."""

from pathlib import Path

import pytest
from conftest import FakeSampling, FakeStorage

from truman_director import plugin
from truman_director.storage import KEY


async def test_snapshot_init_tick_and_restart(monkeypatch):
    storage = FakeStorage()
    sampling = FakeSampling()
    monkeypatch.setattr(plugin, "_storage", storage)
    monkeypatch.setattr(plugin, "_sampling", sampling)
    monkeypatch.setattr(plugin, "_world", None)
    assert await plugin._tool_world("get_snapshot") == {"value": None}
    await plugin._tool_world("init", scenario="cafe_town")
    assert (await plugin._tool_world("get_snapshot"))["value"] == storage.data[KEY]["value"]
    assert not sampling.calls  # Reading and initializing never ask the model.
    await plugin._tool_world("tick", n=1)
    expected = storage.data[KEY]["value"]
    monkeypatch.setattr(plugin, "_world", None)
    assert await plugin._tool_world("get_snapshot") == {"value": expected}
    assert plugin._world is None  # A read does not create/restore mutable world state.
    await plugin._tool_world("tick", n=1)
    assert plugin._world.current_tick == 2


async def test_snapshot_does_not_hide_storage_failure(monkeypatch):
    class DeniedStorage:
        async def get(self, key, *, scope):
            raise RuntimeError("forbidden_scope")

    monkeypatch.setattr(plugin, "_storage", DeniedStorage())
    with pytest.raises(RuntimeError, match="forbidden_scope"):
        await plugin._tool_world("get_snapshot")


def test_frontend_uses_snapshot_action_not_app_storage():
    source = (Path(__file__).parents[1] / "bundle/app.js").read_text(encoding="utf-8")
    assert 'invokeWorld({ action: "get_snapshot" })' in source
    assert "anna.storage.get" not in source
    assert "aps.scope.app.read" not in plugin.MANIFEST["host_capabilities"]
    assert "aps.scope.app.write" not in plugin.MANIFEST["host_capabilities"]
