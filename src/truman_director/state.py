"""WorldState data model — the single source of truth for the simulated town."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

# Cap on the in-memory events list. ``snapshot()`` already feeds only the last
# 20 events to the model, but without a cap the list grows without bound — a
# long run (50-100 ticks * multiple events) would leak memory. 500 is much
# larger than 20, so the buffer comfortably covers the snapshot window +
# timeline (bundle shows 30) + any future event-replay feature, while keeping a
# long run bounded.
MAX_EVENTS = 500

# Day stories kept in the snapshot (DESIGN §5.3): the story feed shows a week
# of the town's life without bloating the 64KB APS KV value.
MAX_STORIES = 7


@dataclass
class DayStory:
    """Prose retelling of one simulated day, produced by engine.narrate."""

    day: int
    tick_from: int
    tick_to: int
    story: str = ""
    cliffhanger: str = ""  # the open thread tomorrow picks up — the return hook


def story_to_dict(s: DayStory) -> dict:
    return {
        "day": s.day,
        "tick_from": s.tick_from,
        "tick_to": s.tick_to,
        "story": s.story,
        "cliffhanger": s.cliffhanger,
    }


def story_from_dict(sd: dict) -> DayStory:
    return DayStory(
        day=sd["day"],
        tick_from=sd.get("tick_from", 0),
        tick_to=sd.get("tick_to", 0),
        story=sd.get("story", ""),
        cliffhanger=sd.get("cliffhanger", ""),
    )


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
    # UI localization (zh/en toggle): canonical `name` is English; scenario
    # presets also fill `name_zh`. Empty string → bundle falls back to `name`.
    name_zh: str = ""
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
    # What the resident is currently after, in their own framing. Prefilled by
    # scenario seeds (M1.2 dramatic tension) or a custom spec's agent entry;
    # reflection (M2) will evolve it. Surfaced to decide() via world_view and
    # to the director via get_agent.
    goal: str = ""
    # Localization (zh/en toggle): canonical names are English; presets also
    # carry the zh variants. `goal` is authored in Chinese (scenario seeds),
    # `goal_en` is its English mirror — engine picks by world.lang.
    name_zh: str = ""
    occupation_zh: str = ""
    goal_en: str = ""
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
        name_zh=ld.get("name_zh", ""),
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
        goal=ad.get("goal", ""),
        name_zh=ad.get("name_zh", ""),
        occupation_zh=ad.get("occupation_zh", ""),
        goal_en=ad.get("goal_en", ""),
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


def event_to_dict(e: Event) -> dict:
    """Serialize one Event for snapshot / timeline / agent-detail responses.

    Single serializer so every surface (prompt view, storage, bundle timeline)
    sees the exact same event shape.
    """
    return {
        "id": e.id,
        "tick": e.tick,
        "event_type": e.event_type,
        "actor_agent_id": e.actor_agent_id,
        "target_agent_id": e.target_agent_id,
        "location_id": e.location_id,
        "description": e.description,
        "importance": e.importance,
    }


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
    # Output language for LLM prose (decide reasons / day stories): "zh"|"en".
    # Set at init/reset, switchable via tick; persisted in the snapshot so a
    # restart keeps the town's language.
    lang: str = "zh"
    # Day tracking (DESIGN §5.1 / M1.5): day 1 is the opening day; a midnight
    # crossing rolls it over and marks a checkpoint for the day-close routine.
    day: int = 1
    day_start_tick: int = 0  # first tick of the current day (story span bookkeeping)
    locations: dict[str, Location] = field(default_factory=dict)
    agents: dict[str, Agent] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    stories: list[DayStory] = field(default_factory=list)  # bounded at MAX_STORIES
    _pending_injections: list[dict] = field(default_factory=list)

    def advance_tick(self) -> bool:
        """Advance one tick. Returns True when the clock crossed midnight —
        the caller (engine.tick) then runs the day-close routine after the
        tick's decide/apply/save completes, so the story covers the day that
        just ENDED, including its final tick."""
        h, m = map(int, self.world_time.split(":"))
        dt = datetime(2000, 1, 1, h, m) + timedelta(minutes=self.tick_minutes)
        rolled = dt.day != 1  # anchor day is the 1st; any rollover shows as day 2
        self.world_time = dt.strftime("%H:%M")
        self.current_tick += 1
        if rolled:
            self.day += 1
            self.day_start_tick = self.current_tick
        return rolled

    def snapshot(self) -> dict:
        """JSON-serializable dict — fed to sampling prompt + stored in APS KV."""
        return {
            "run_id": self.run_id,
            "scenario": self.scenario,
            "current_tick": self.current_tick,
            "world_time": self.world_time,
            "tick_minutes": self.tick_minutes,
            "lang": self.lang,
            "day": self.day,
            "day_start_tick": self.day_start_tick,
            "locations": {
                lid: {
                    "id": loc.id,
                    "name": loc.name,
                    "name_zh": loc.name_zh,
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
                    "name_zh": a.name_zh,
                    "occupation": a.occupation,
                    "occupation_zh": a.occupation_zh,
                    "home_location_id": a.home_location_id,
                    "current_location_id": a.current_location_id,
                    "personality": a.personality,
                    "goal": a.goal,
                    "goal_en": a.goal_en,
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
                event_to_dict(e)
                for e in self.events[-20:]  # last 20 events for context window
            ],
            "stories": [story_to_dict(s) for s in self.stories[-MAX_STORIES:]],
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
        stories = [story_from_dict(sd) for sd in data.get("stories", [])]

        return cls(
            run_id=data["run_id"],
            scenario=data["scenario"],
            current_tick=data.get("current_tick", 0),
            world_time=data.get("world_time", "08:00"),
            tick_minutes=data.get("tick_minutes", 5),
            # 0.3.x snapshots predate lang — default zh matches the era's
            # hardcoded "reasons in Chinese" prompt.
            lang=data.get("lang", "zh"),
            # 0.3.x snapshots predate day tracking — default day 1, tick 0. The
            # first midnight crossing after upgrade lands them on the new path.
            day=data.get("day", 1),
            day_start_tick=data.get("day_start_tick", 0),
            locations=locations,
            agents=agents,
            events=events,
            stories=stories,
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
        # Bounded growth: keep only the most recent MAX_EVENTS. The snapshot
        # window (20) and timeline (30) both read from the tail, so trimming the
        # head never loses anything the model or UI can see.
        if len(self.events) > MAX_EVENTS:
            del self.events[:-MAX_EVENTS]
