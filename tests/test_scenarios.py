from datetime import UTC, datetime

import pytest

from truman_director.errors import InvalidWorldSpecError, UnknownScenarioError
from truman_director.scenarios import SCENARIOS, build, build_from_spec


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


# ── custom world spec (build_from_spec) ───────────────────────────────

_START = datetime(2026, 6, 19, 8, 0, tzinfo=UTC)


def _valid_spec() -> dict:
    return {
        "name": "Test Town",
        "world_time": "09:30",
        "locations": [
            {"id": "loc_a", "name": "Cafe A", "type": "cafe", "x": 10, "y": 20, "capacity": 5},
            {"id": "loc_b", "name": "Park B", "type": "park", "x": 50, "y": 60},
        ],
        "agents": [
            {
                "id": "x",
                "name": "Xena",
                "occupation": "Cook",
                "home_location_id": "loc_a",
                "personality": {"openness": 0.5},
            },
            {"id": "y", "name": "Yan", "occupation": "Gardener", "home_location_id": "loc_b"},
        ],
    }


def test_build_from_spec_constructs_custom_world():
    world = build_from_spec(_valid_spec(), _START)
    assert world.scenario == "Test Town"
    assert world.world_time == "09:30"
    assert set(world.locations) == {"loc_a", "loc_b"}
    assert set(world.agents) == {"x", "y"}
    # current_location defaults to home when omitted
    assert world.agents["x"].current_location_id == "loc_a"
    assert world.agents["x"].personality == {"openness": 0.5}
    # capacity default applied where omitted
    assert world.locations["loc_b"].capacity == 10


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda s: s.pop("locations"), "locations"),
        (lambda s: s.__setitem__("agents", []), "agents"),
        (lambda s: s["agents"][0].pop("home_location_id"), "home_location_id"),
        (lambda s: s["agents"][0].__setitem__("home_location_id", "ghost"), "not in locations"),
        (lambda s: s["locations"][0].__setitem__("type", "planet"), "type"),
        (lambda s: s["locations"][0].__setitem__("x", 200), "x"),
        (lambda s: s["locations"][0].__setitem__("capacity", 0), "capacity"),
        (lambda s: s["agents"][0].__setitem__("personality", {"openness": 2.0}), "personality"),
        (lambda s: s["agents"].append(dict(s["agents"][0])), "duplicate agent id"),
        (lambda s: s.__setitem__("world_time", "25:00"), "world_time"),
    ],
)
def test_build_from_spec_rejects_bad_input(mutate, needle):
    spec = _valid_spec()
    mutate(spec)
    with pytest.raises(InvalidWorldSpecError) as exc_info:
        build_from_spec(spec, _START)
    assert needle in str(exc_info.value)
