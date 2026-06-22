"""WorldState data model — the single source of truth for the simulated town."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum


class LocationType(StrEnum):
    CAFE = "cafe"
    PARK = "park"
    LIBRARY = "library"
    HOME = "home"
    STREET = "street"


@dataclass
class Location:
    id: str
    name: str
    type: LocationType
    x: int  # 0-100, UI percentage
    y: int
    capacity: int = 10
    description: str = ""
    occupants: set[str] = field(default_factory=set)


@dataclass
class Relationship:
    other_agent_id: str
    familiarity: float = 0.0
    trust: float = 0.5
    affinity: float = 0.0
    last_interaction_tick: int = 0


@dataclass
class Agent:
    id: str
    name: str
    occupation: str
    home_location_id: str
    current_location_id: str
    personality: dict = field(default_factory=dict)
    # What the agent is doing right now: idle / work / rest. Set by apply_event
    # on work|rest decisions; move|talk|world_change reset it to idle (a new
    # action ends the previous activity). Before this existed, work|rest events
    # left world state untouched — "alice is working" was only a timeline line,
    # not a real state the model or UI could read back.
    current_activity: str = "idle"
    relationships: dict[str, Relationship] = field(default_factory=dict)


@dataclass
class Event:
    id: str
    tick: int
    event_type: str  # move / talk / work / rest / director_inject / world_change
    actor_agent_id: str | None
    target_agent_id: str | None = None
    location_id: str | None = None
    description: str = ""
    payload: dict = field(default_factory=dict)
    importance: float = 0.5
    created_at: float = 0.0


def location_from_dict(ld: dict) -> Location:
    """Parse one location dict (snapshot entry or world-spec entry) into a Location.

    Shared by ``WorldState.from_snapshot`` and ``scenarios.build_from_spec`` so the two
    ingestion paths can never drift apart.
    """
    return Location(
        id=ld["id"],
        name=ld["name"],
        type=LocationType(ld["type"]),
        x=ld["x"],
        y=ld["y"],
        capacity=ld.get("capacity", 10),
        description=ld.get("description", ""),
        occupants=set(ld.get("occupants", [])),
    )


def agent_from_dict(ad: dict) -> Agent:
    """Parse one agent dict (snapshot entry or world-spec entry) into an Agent."""
    return Agent(
        id=ad["id"],
        name=ad["name"],
        occupation=ad["occupation"],
        home_location_id=ad["home_location_id"],
        current_location_id=ad["current_location_id"],
        personality=ad.get("personality", {}),
        current_activity=ad.get("current_activity", "idle"),
        relationships={
            rid: Relationship(
                other_agent_id=rid,
                familiarity=rd.get("familiarity", 0.0),
                trust=rd.get("trust", 0.5),
                affinity=rd.get("affinity", 0.0),
                last_interaction_tick=rd.get("last_interaction_tick", 0),
            )
            for rid, rd in ad.get("relationships", {}).items()
        },
    )


def event_from_dict(ed: dict) -> Event:
    """Parse one event dict (snapshot entry) into an Event.

    Shares the parser with ``WorldState.from_snapshot``. ``snapshot()`` drops the
    transient ``payload`` / ``created_at`` fields, so they fall back to the
    dataclass defaults on the way back in — downstream never reads them.
    """
    return Event(
        id=ed["id"],
        tick=ed["tick"],
        event_type=ed["event_type"],
        actor_agent_id=ed.get("actor_agent_id"),
        target_agent_id=ed.get("target_agent_id"),
        location_id=ed.get("location_id"),
        description=ed.get("description", ""),
        importance=ed.get("importance", 0.5),
    )


@dataclass
class WorldState:
    run_id: str
    scenario: str
    current_tick: int = 0
    world_time: str = "08:00"  # HH:MM
    tick_minutes: int = 5  # 1 tick = 5 simulated minutes
    locations: dict[str, Location] = field(default_factory=dict)
    agents: dict[str, Agent] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    _pending_injections: list[dict] = field(default_factory=list)

    def advance_tick(self) -> None:
        h, m = map(int, self.world_time.split(":"))
        dt = datetime(2000, 1, 1, h, m) + timedelta(minutes=self.tick_minutes)
        self.world_time = dt.strftime("%H:%M")
        self.current_tick += 1

    def snapshot(self) -> dict:
        """JSON-serializable dict — fed to sampling prompt + stored in APS KV."""
        return {
            "run_id": self.run_id,
            "scenario": self.scenario,
            "current_tick": self.current_tick,
            "world_time": self.world_time,
            "tick_minutes": self.tick_minutes,
            "locations": {
                lid: {
                    "id": loc.id,
                    "name": loc.name,
                    "type": loc.type.value,
                    "x": loc.x,
                    "y": loc.y,
                    "capacity": loc.capacity,
                    "description": loc.description,
                    "occupants": sorted(loc.occupants),
                }
                for lid, loc in self.locations.items()
            },
            "agents": {
                aid: {
                    "id": a.id,
                    "name": a.name,
                    "occupation": a.occupation,
                    "home_location_id": a.home_location_id,
                    "current_location_id": a.current_location_id,
                    "personality": a.personality,
                    "current_activity": a.current_activity,
                    "relationships": {
                        rid: {
                            "familiarity": rel.familiarity,
                            "trust": rel.trust,
                            "affinity": rel.affinity,
                            "last_interaction_tick": rel.last_interaction_tick,
                        }
                        for rid, rel in a.relationships.items()
                    },
                }
                for aid, a in self.agents.items()
            },
            "events": [
                {
                    "id": e.id,
                    "tick": e.tick,
                    "event_type": e.event_type,
                    "actor_agent_id": e.actor_agent_id,
                    "target_agent_id": e.target_agent_id,
                    "location_id": e.location_id,
                    "description": e.description,
                    "importance": e.importance,
                }
                for e in self.events[-20:]  # last 20 events for context window
            ],
        }

    @classmethod
    def from_snapshot(cls, data: dict) -> WorldState:
        """Reconstruct from APS KV payload (shares parsers with scenarios.build_from_spec).

        Restores ``events`` too, so a plugin restart can resume the world with its
        history intact — the snapshot is the single source of truth (CLAUDE.md red
        line 2), and the in-memory events list is just its writable mirror.
        """
        locations = {lid: location_from_dict(ld) for lid, ld in data.get("locations", {}).items()}
        agents = {aid: agent_from_dict(ad) for aid, ad in data.get("agents", {}).items()}
        events = [event_from_dict(ed) for ed in data.get("events", [])]

        return cls(
            run_id=data["run_id"],
            scenario=data["scenario"],
            current_tick=data.get("current_tick", 0),
            world_time=data.get("world_time", "08:00"),
            tick_minutes=data.get("tick_minutes", 5),
            locations=locations,
            agents=agents,
            events=events,
        )

    def apply_event(self, evt: dict) -> None:
        """Apply a single decision event to world state.

        Every action the model can return (move|rest|work|talk, per
        DECISION_SCHEMA) now mutates real state — there are no "log-only" actions.
        move/talk/world_change reset the actor's activity to idle, since a new
        action ends whatever they were doing; work/rest set it accordingly.
        """
        agent_id = evt.get("agent_id")
        action = evt.get("action")
        target = evt.get("target")
        agent = self.agents.get(agent_id) if agent_id else None

        if action == "move" and agent and target in self.locations:
            old_loc = self.locations.get(agent.current_location_id)
            if old_loc:
                old_loc.occupants.discard(agent_id)
            new_loc = self.locations[target]
            new_loc.occupants.add(agent_id)
            agent.current_location_id = target
            agent.current_activity = "idle"

        elif action == "talk" and agent and target:
            other = self.agents.get(target)
            if other:
                # Bidirectional: a conversation makes both parties more familiar.
                for who, other_id in ((agent, target), (other, agent_id)):
                    rel = who.relationships.setdefault(
                        other_id, Relationship(other_agent_id=other_id)
                    )
                    rel.familiarity = min(1.0, rel.familiarity + 0.05)
                    rel.last_interaction_tick = self.current_tick
                agent.current_activity = "idle"
                other.current_activity = "idle"

        elif action == "work" and agent:
            # Working pins the agent to their current location with an active
            # activity flag — occupants don't change, but the state is now
            # observable to the model and UI instead of being a log-only line.
            agent.current_activity = "work"

        elif action == "rest" and agent:
            agent.current_activity = "rest"

    def record_event(self, evt: dict) -> None:
        event = Event(
            id=f"e_{uuid.uuid4().hex[:8]}",
            tick=self.current_tick,
            event_type=evt.get("action", "unknown"),
            actor_agent_id=evt.get("agent_id"),
            target_agent_id=evt.get("target") if evt.get("action") == "talk" else None,
            location_id=(evt.get("target") if evt.get("action") in ("move", "work") else None),
            description=evt.get("reason", ""),
            importance=evt.get("importance", 0.5),
        )
        self.events.append(event)
