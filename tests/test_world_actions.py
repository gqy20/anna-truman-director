"""world tool actions beyond init/tick/inject_event (DESIGN §7, M1.1).

reset / list_scenarios / get_agent / get_timeline are read-or-rebuild paths over
the in-memory world — they need no sampling, so they are unit-tested directly
against the dispatcher with a live module world and a fake storage.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from conftest import FakeStorage

from truman_director import plugin
from truman_director.errors import AgentNotFoundError, InvalidWorldSpecError
from truman_director.scenarios import build


@pytest.fixture
def live_world(monkeypatch):
    """A cafe_town world wired into the plugin's module state."""
    monkeypatch.setattr(plugin, "_world", build("cafe_town", datetime(2026, 8, 15, tzinfo=UTC)))
    monkeypatch.setattr(plugin, "_storage", FakeStorage())


async def test_reset_mints_fresh_run_and_overwrites_snapshot(monkeypatch):
    monkeypatch.setattr(plugin, "_world", None)
    storage = FakeStorage()
    storage.data["truman:run:world"] = {"value": {"run_id": "run_old"}}
    monkeypatch.setattr(plugin, "_storage", storage)

    out = await plugin._tool_world(action="reset", scenario="cafe_town")

    assert out["tick"] == 0
    assert storage.data["truman:run:world"]["value"]["run_id"] != "run_old"
    assert plugin._world.run_id.startswith("run_")


async def test_reset_without_scenario_or_spec_is_loud():
    with pytest.raises(InvalidWorldSpecError):
        await plugin._tool_world(action="reset")


async def test_list_scenarios_returns_storefront_metadata(live_world):
    out = await plugin._tool_world(action="list_scenarios")
    cafe = next(s for s in out["scenarios"] if s["id"] == "cafe_town")
    assert cafe["name"] == "Cafe Town"
    assert cafe["description"]


async def test_get_agent_returns_dossier(live_world):
    world = plugin._world
    # Manufacture a talk so the dossier has a relationship + an event to show.
    world.apply_event({"agent_id": "alice", "action": "talk", "target": "bob", "reason": "chat"})
    world.record_event({"agent_id": "alice", "action": "talk", "target": "bob", "reason": "chat"})

    out = await plugin._tool_world(action="get_agent", agent_id="alice")

    assert out["agent"]["id"] == "alice"
    assert out["agent"]["occupation"] == "Barista"
    assert out["location"]["id"] == "loc_alice_home"
    rel = next(r for r in out["relationships"] if r["agent_id"] == "bob")
    assert rel["name"] == "Bob"
    assert 0 < rel["familiarity"] <= 1
    assert any(e["event_type"] == "talk" for e in out["recent_events"])


async def test_get_agent_unknown_id_is_loud(live_world):
    with pytest.raises(AgentNotFoundError) as exc:
        await plugin._tool_world(action="get_agent", agent_id="nobody")
    assert exc.value.code == -32005


async def test_get_timeline_filters_and_limits(live_world):
    world = plugin._world
    for i in range(12):
        world.record_event(
            {"agent_id": "alice", "action": "move", "target": "loc_cafe", "reason": f"wander {i}"}
        )
    world.record_event({"agent_id": "bob", "action": "rest", "target": None, "reason": "nap"})

    out = await plugin._tool_world(action="get_timeline", limit=5)
    assert len(out["events"]) == 5
    # newest last→returned tail is most recent; limit keeps the LAST events
    assert out["events"][-1]["event_type"] == "rest"

    talks = await plugin._tool_world(action="get_timeline", agent_id="bob", limit=100)
    assert all(
        e["actor_agent_id"] == "bob" or e["target_agent_id"] == "bob" for e in talks["events"]
    )
    assert len(talks["events"]) == 1

    moves = await plugin._tool_world(action="get_timeline", event_type="move")
    assert len(moves["events"]) == 12


async def test_unknown_action_is_loud(live_world):
    with pytest.raises(ValueError, match="unknown action"):
        await plugin._tool_world(action="teleport")
