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
class Memory:
    tick: int
    content: str
    importance: float = 0.5
    memory_type: str = "observation"  # observation / interaction / reflection


@dataclass
class Agent:
    id: str
    name: str
    occupation: str
    home_location_id: str
    current_location_id: str
    personality: dict = field(default_factory=dict)
    memories: list[Memory] = field(default_factory=list)
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
        """Reconstruct from APS KV payload (shares parsers with scenarios.build_from_spec)."""
        locations = {lid: location_from_dict(ld) for lid, ld in data.get("locations", {}).items()}
        agents = {aid: agent_from_dict(ad) for aid, ad in data.get("agents", {}).items()}

        return cls(
            run_id=data["run_id"],
            scenario=data["scenario"],
            current_tick=data.get("current_tick", 0),
            world_time=data.get("world_time", "08:00"),
            tick_minutes=data.get("tick_minutes", 5),
            locations=locations,
            agents=agents,
            events=[],
        )

    def apply_event(self, evt: dict) -> None:
        """Apply a single decision event to world state."""
        agent_id = evt.get("agent_id")
        action = evt.get("action")
        target = evt.get("target")

        if action == "move" and agent_id and target:
            agent = self.agents.get(agent_id)
            if agent and target in self.locations:
                old_loc = self.locations.get(agent.current_location_id)
                if old_loc:
                    old_loc.occupants.discard(agent_id)
                new_loc = self.locations[target]
                new_loc.occupants.add(agent_id)
                agent.current_location_id = target

        elif action == "talk" and agent_id and target:
            agent = self.agents.get(agent_id)
            other = self.agents.get(target)
            if agent and other:
                # Bidirectional: a conversation makes both parties more familiar.
                for who, other_id in ((agent, target), (other, agent_id)):
                    rel = who.relationships.setdefault(
                        other_id, Relationship(other_agent_id=other_id)
                    )
                    rel.familiarity = min(1.0, rel.familiarity + 0.05)
                    rel.last_interaction_tick = self.current_tick

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
