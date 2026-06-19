from datetime import UTC, datetime

import pytest

from truman_director.errors import UnknownScenarioError
from truman_director.scenarios import SCENARIOS, build


def test_cafe_town_builds_consistent_world():
    world = build("cafe_town", datetime(2026, 6, 19, 8, 0, tzinfo=UTC))
    assert world.scenario == "cafe_town"
    assert world.world_time == "08:00"
    assert {"alice", "bob", "truman"} <= set(world.agents)
    # every agent's home must exist as a location
    for agent in world.agents.values():
        assert agent.home_location_id in world.locations


def test_unknown_scenario_raises():
    with pytest.raises(UnknownScenarioError):
        build("nope", datetime(2026, 6, 19, tzinfo=UTC))


def test_registry_only_has_documented_scenarios():
    assert sorted(SCENARIOS) == ["cafe_town"]
