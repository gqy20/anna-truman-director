"""Acceptance-level regression checks mapped to the Marketplace QA report."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from conftest import FakeSampling, FakeStorage

from truman_director.engine import apply_inject_event, tick
from truman_director.errors import AgentNotFoundError, InvalidEventSpecError
from truman_director.scenarios import build
from truman_director.state import WorldState


def _world() -> WorldState:
    return build("cafe_town", datetime(2026, 9, 1, 8, 0, tzinfo=UTC))


async def test_tc04_targeted_opportunity_is_attributed_and_visible_to_model():
    world = _world()
    sampling = FakeSampling(
        events=[
            {
                "agent_id": "alice",
                "action": "talk",
                "target": "bob",
                "reason": "Alice tells Bob about the unexpected grant.",
            }
        ]
    )
    storage = FakeStorage()

    apply_inject_event(
        world,
        {
            "agent_id": "alice",
            "action": "world_change",
            "reason": "Alice receives an unexpected 500 yuan opportunity grant.",
            "importance": 0.95,
        },
    )
    await tick(world, sampling, storage, n=1)

    model_view = json.loads(sampling.calls[0]["messages"][0]["content"]["text"])
    injected = next(e for e in model_view["events"] if "500 yuan" in e["description"])
    assert injected["actor_agent_id"] == "alice"
    assert injected["importance"] == 0.95
    assert world.agents["alice"].relationships["bob"].familiarity == pytest.approx(0.05)


async def test_tc05_consequences_survive_snapshot_restore_and_continue():
    world = _world()
    storage = FakeStorage()
    sampling = FakeSampling(
        events=[
            {
                "agent_id": "alice",
                "action": "talk",
                "target": "bob",
                "reason": "Alice asks Bob how the grant could change the cafe.",
            }
        ]
    )
    apply_inject_event(
        world,
        {
            "agent_id": "alice",
            "action": "world_change",
            "reason": "Alice receives a grant that may change the cafe.",
        },
    )
    await tick(world, sampling, storage, n=1)

    restored = WorldState.from_snapshot(storage.data["truman:run:world"]["value"])
    before = restored.agents["alice"].relationships["bob"].familiarity
    assert any("receives a grant" in e.description for e in restored.events)

    await tick(restored, sampling, storage, n=1)
    assert restored.current_tick == 2
    assert restored.agents["alice"].relationships["bob"].familiarity > before
    assert any("receives a grant" in e.description for e in restored.events)


@pytest.mark.parametrize(
    ("event", "error"),
    [
        ({"action": "teleport", "reason": "invalid"}, InvalidEventSpecError),
        (
            {"action": "move", "agent_id": "alice", "target": "missing", "reason": "x"},
            InvalidEventSpecError,
        ),
        (
            {"action": "talk", "agent_id": "alice", "target": "nobody", "reason": "x"},
            AgentNotFoundError,
        ),
        ({"action": "world_change", "agent_id": "nobody", "reason": "x"}, AgentNotFoundError),
        ({"action": "world_change", "reason": ""}, InvalidEventSpecError),
        ({"action": "world_change", "reason": "x", "importance": 2}, InvalidEventSpecError),
    ],
)
def test_security_rejects_invalid_director_events(event: dict, error: type[Exception]):
    with pytest.raises(error):
        apply_inject_event(_world(), event)


def test_security_preserves_markup_as_data_not_code():
    world = _world()
    payload = '<img src=x onerror="window.__qa_xss=1">'
    apply_inject_event(world, {"reason": payload})
    queued = world._pending_injections[0]
    assert queued["reason"] == payload
    assert queued["action"] == "world_change"
