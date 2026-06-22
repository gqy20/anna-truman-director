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


def test_snapshot_roundtrip_preserves_events():
    """from_snapshot must restore events — the snapshot is the single source of
    truth, so a plugin restart resumes the world WITH its history. Without this,
    Agent-driven restarts drop every recorded event (timeline empty, model loses
    recent context)."""
    from truman_director.state import Agent, Location, LocationType

    world = WorldState(run_id="r1", scenario="cafe_town")
    world.locations = {
        "cafe": Location(id="cafe", name="Cafe", type=LocationType.CAFE, x=50, y=50),
    }
    world.agents = {
        "alice": Agent(
            id="alice",
            name="Alice",
            occupation="x",
            home_location_id="cafe",
            current_location_id="cafe",
        )
    }
    world.current_tick = 7
    world.apply_event({"agent_id": "alice", "action": "work", "target": "cafe", "reason": "shift"})
    world.record_event({"agent_id": "alice", "action": "work", "target": "cafe", "reason": "shift"})

    restored = WorldState.from_snapshot(world.snapshot())
    assert restored.current_tick == 7
    assert len(restored.events) == 1
    assert restored.events[0].description == "shift"
    assert restored.events[0].event_type == "work"


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


def _two_agent_world():
    """Helper: cafe + two agents at the cafe, for activity tests.

    Seeds occupants the same way plugin._tool_world('init') does (each agent
    added to its current_location_id's occupants) so tests reflect a real
    post-init world, not a half-built one.
    """
    from truman_director.state import Agent, Location, LocationType

    world = WorldState(run_id="r1", scenario="cafe_town")
    world.locations = {
        "cafe": Location(id="cafe", name="Cafe", type=LocationType.CAFE, x=50, y=50),
        "park": Location(id="park", name="Park", type=LocationType.PARK, x=10, y=10),
    }
    world.agents = {
        "a": Agent(
            id="a",
            name="A",
            occupation="barista",
            home_location_id="cafe",
            current_location_id="cafe",
        ),
        "b": Agent(
            id="b",
            name="B",
            occupation="writer",
            home_location_id="cafe",
            current_location_id="cafe",
        ),
    }
    for agent in world.agents.values():
        world.locations[agent.current_location_id].occupants.add(agent.id)
    return world


def test_work_sets_activity_and_pins_to_location():
    """work is now real state: the agent's current_activity flips to 'work' and
    they stay in their current location (occupants unchanged). Before this fix,
    a work event left the world untouched — only a log line."""
    world = _two_agent_world()
    world.apply_event({"agent_id": "a", "action": "work", "reason": "opens the cafe"})
    assert world.agents["a"].current_activity == "work"
    # pinned to current location — not relocated, but occupants reflect presence
    assert "a" in world.locations["cafe"].occupants


def test_rest_sets_activity():
    world = _two_agent_world()
    world.apply_event({"agent_id": "a", "action": "work", "reason": "shift"})
    world.apply_event({"agent_id": "a", "action": "rest", "reason": "break"})
    assert world.agents["a"].current_activity == "rest"


def test_move_resets_activity_to_idle():
    """A new action ends the previous activity: moving out ends a work shift."""
    world = _two_agent_world()
    world.apply_event({"agent_id": "a", "action": "work", "reason": "shift"})
    assert world.agents["a"].current_activity == "work"
    world.apply_event({"agent_id": "a", "action": "move", "target": "park", "reason": "off-shift"})
    assert world.agents["a"].current_activity == "idle"


def test_talk_resets_both_parties_activity():
    """A conversation interrupts whatever both parties were doing."""
    world = _two_agent_world()
    world.apply_event({"agent_id": "a", "action": "work", "reason": "shift"})
    world.apply_event({"agent_id": "b", "action": "rest", "reason": "lounging"})
    world.apply_event({"agent_id": "a", "action": "talk", "target": "b", "reason": "greeting"})
    assert world.agents["a"].current_activity == "idle"
    assert world.agents["b"].current_activity == "idle"


def test_activity_roundtrips_through_snapshot():
    """current_activity must survive snapshot/from_snapshot so a plugin restart
    doesn't forget everyone was mid-shift."""
    world = _two_agent_world()
    world.apply_event({"agent_id": "a", "action": "work", "reason": "shift"})
    snap = world.snapshot()
    assert snap["agents"]["a"]["current_activity"] == "work"
    restored = WorldState.from_snapshot(snap)
    assert restored.agents["a"].current_activity == "work"


def test_old_snapshot_without_activity_defaults_to_idle():
    """Backward compat: a snapshot written before current_activity existed has
    no such key — agents must default to idle, not KeyError."""
    world = _two_agent_world()
    snap = world.snapshot()
    # simulate a legacy snapshot: strip the new field
    for a in snap["agents"].values():
        a.pop("current_activity", None)
    restored = WorldState.from_snapshot(snap)
    assert restored.agents["a"].current_activity == "idle"
