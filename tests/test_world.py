from truman_director.state import WorldState


def test_advance_tick_increments():
    world = WorldState(run_id="r1", scenario="cafe_town", world_time="08:00", tick_minutes=5)
    world.advance_tick()
    assert world.current_tick == 1
    assert world.world_time == "08:05"


def test_advance_tick_crosses_hour():
    world = WorldState(run_id="r1", scenario="cafe_town", world_time="08:58", tick_minutes=5)
    world.advance_tick()
    assert world.world_time == "09:03"


def test_snapshot_roundtrip_preserves_basics():
    world = WorldState(run_id="r1", scenario="cafe_town", world_time="07:30")
    snap = world.snapshot()
    restored = WorldState.from_snapshot(snap)
    assert restored.run_id == "r1"
    assert restored.world_time == "07:30"


def test_apply_move_event_relocates_agent():
    from truman_director.state import Agent, Location, LocationType

    world = WorldState(run_id="r1", scenario="cafe_town")
    world.locations = {
        "home": Location(id="home", name="Home", type=LocationType.HOME, x=0, y=0, occupants={"a"}),
        "cafe": Location(id="cafe", name="Cafe", type=LocationType.CAFE, x=50, y=50),
    }
    world.agents = {
        "a": Agent(
            id="a", name="A", occupation="x", home_location_id="home", current_location_id="home"
        )
    }
    world.apply_event({"agent_id": "a", "action": "move", "target": "cafe", "reason": "coffee"})
    assert world.agents["a"].current_location_id == "cafe"
    assert "a" in world.locations["cafe"].occupants
    assert "a" not in world.locations["home"].occupants


def test_snapshot_roundtrip_preserves_relationships():
    from truman_director.state import Agent, Relationship

    world = WorldState(run_id="r1", scenario="cafe_town")
    world.agents = {
        "alice": Agent(
            id="alice",
            name="Alice",
            occupation="x",
            home_location_id="h",
            current_location_id="h",
            relationships={"bob": Relationship(other_agent_id="bob", familiarity=0.3)},
        )
    }
    snap = world.snapshot()
    restored = WorldState.from_snapshot(snap)
    assert restored.agents["alice"].relationships["bob"].familiarity == 0.3


def test_apply_talk_event_is_bidirectional():
    from truman_director.state import Agent, Location, LocationType

    world = WorldState(run_id="r1", scenario="cafe_town")
    world.locations = {
        "cafe": Location(
            id="cafe", name="Cafe", type=LocationType.CAFE, x=0, y=0, occupants={"a", "b"}
        ),
    }
    world.agents = {
        "a": Agent(
            id="a", name="A", occupation="x", home_location_id="cafe", current_location_id="cafe"
        ),
        "b": Agent(
            id="b", name="B", occupation="y", home_location_id="cafe", current_location_id="cafe"
        ),
    }
    world.apply_event({"agent_id": "a", "action": "talk", "target": "b", "reason": "chat"})
    # a conversation grows familiarity in BOTH directions
    assert world.agents["a"].relationships["b"].familiarity > 0
    assert world.agents["b"].relationships["a"].familiarity > 0
