"""Scenario presets — builder functions that construct initial WorldState."""

from __future__ import annotations

from datetime import datetime

from .errors import InvalidWorldSpecError, UnknownScenarioError
from .state import (
    Agent,
    Location,
    LocationType,
    WorldState,
    agent_from_dict,
    location_from_dict,
)


def _cafe_town(start: datetime) -> WorldState:
    """Cafe Town: 3 residents, cafe is the social hub."""
    return WorldState(
        run_id=f"run_{int(start.timestamp() * 1000)}",
        scenario="cafe_town",
        world_time="08:00",
        locations={
            "loc_alice_home": Location(
                id="loc_alice_home",
                name="Alice's Apartment",
                type=LocationType.HOME,
                x=20,
                y=30,
                capacity=2,
                description="Cozy studio above the bakery.",
            ),
            "loc_bob_home": Location(
                id="loc_bob_home",
                name="Bob's House",
                type=LocationType.HOME,
                x=75,
                y=70,
                capacity=3,
                description="Small house near the park.",
            ),
            "loc_truman_home": Location(
                id="loc_truman_home",
                name="Truman's Place",
                type=LocationType.HOME,
                x=50,
                y=80,
                capacity=2,
                description="The protagonist's home.",
            ),
            "loc_cafe": Location(
                id="loc_cafe",
                name="Bean & Bite",
                type=LocationType.CAFE,
                x=55,
                y=40,
                capacity=8,
                description="Town's social center. Best espresso.",
            ),
            "loc_park": Location(
                id="loc_park",
                name="Riverside Park",
                type=LocationType.PARK,
                x=30,
                y=65,
                capacity=20,
                description="Quiet park with a pond.",
            ),
            "loc_library": Location(
                id="loc_library",
                name="Town Library",
                type=LocationType.LIBRARY,
                x=80,
                y=25,
                capacity=12,
                description="Small but well-stocked.",
            ),
        },
        agents={
            "alice": Agent(
                id="alice",
                name="Alice",
                occupation="Barista",
                home_location_id="loc_alice_home",
                current_location_id="loc_alice_home",
                personality={
                    "openness": 0.8,
                    "conscientiousness": 0.7,
                    "extraversion": 0.7,
                    "agreeableness": 0.8,
                },
            ),
            "bob": Agent(
                id="bob",
                name="Bob",
                occupation="Freelance Writer",
                home_location_id="loc_bob_home",
                current_location_id="loc_bob_home",
                personality={
                    "openness": 0.6,
                    "conscientiousness": 0.4,
                    "extraversion": 0.3,
                    "agreeableness": 0.6,
                },
            ),
            "truman": Agent(
                id="truman",
                name="Truman",
                occupation="Insurance Salesman",
                home_location_id="loc_truman_home",
                current_location_id="loc_truman_home",
                personality={
                    "openness": 0.5,
                    "conscientiousness": 0.6,
                    "extraversion": 0.5,
                    "agreeableness": 0.7,
                },
            ),
        },
    )


SCENARIOS: dict[str, callable] = {
    "cafe_town": _cafe_town,
}


def build(slug: str, start: datetime) -> WorldState:
    if slug not in SCENARIOS:
        raise UnknownScenarioError(f"unknown scenario: {slug!r}; available: {sorted(SCENARIOS)}")
    return SCENARIOS[slug](start)


# ── custom world spec ─────────────────────────────────────────────────


def build_from_spec(spec: dict, start: datetime) -> WorldState:
    """Build a WorldState from a user-supplied world spec (custom residents/locations/time).

    Validates structure + references + value ranges; raises ``InvalidWorldSpecError`` loudly
    (CLAUDE.md red line: failures are loud). Shares the dict→object parsers with
    ``WorldState.from_snapshot`` so spec and snapshot never drift apart.
    """
    _validate_spec(spec)
    locations = {ld["id"]: location_from_dict(ld) for ld in spec["locations"]}
    agents: dict[str, Agent] = {}
    for ad in spec["agents"]:
        entry = dict(ad)
        entry.setdefault("current_location_id", entry["home_location_id"])
        agents[entry["id"]] = agent_from_dict(entry)
    return WorldState(
        run_id=f"run_{int(start.timestamp() * 1000)}",
        scenario=spec.get("name") or "custom",
        world_time=spec.get("world_time", "08:00"),
        locations=locations,
        agents=agents,
    )


def _validate_spec(spec: dict) -> None:
    """Structural + referential + value-range checks. Raises on the first problem."""
    if not isinstance(spec, dict):
        raise InvalidWorldSpecError("spec must be an object")

    locations = spec.get("locations")
    agents = spec.get("agents")
    if not isinstance(locations, list) or not locations:
        raise InvalidWorldSpecError("spec.locations must be a non-empty array")
    if not isinstance(agents, list) or not agents:
        raise InvalidWorldSpecError("spec.agents must be a non-empty array")

    world_time = spec.get("world_time", "08:00")
    if not _is_hhmm(world_time):
        raise InvalidWorldSpecError(f"spec.world_time must be HH:MM, got {world_time!r}")

    loc_ids: set[str] = set()
    for i, ld in enumerate(locations):
        ctx = f"locations[{i}]"
        _require_fields(ld, ("id", "name", "type", "x", "y"), ctx)
        if ld["id"] in loc_ids:
            raise InvalidWorldSpecError(f"duplicate location id: {ld['id']!r}")
        loc_ids.add(ld["id"])
        _check_int_range(ld, "x", 0, 100, f"{ctx}.x")
        _check_int_range(ld, "y", 0, 100, f"{ctx}.y")
        capacity = ld.get("capacity", 10)
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
            raise InvalidWorldSpecError(f"{ctx}.capacity must be a positive int, got {capacity!r}")
        try:
            LocationType(ld["type"])
        except (ValueError, TypeError):
            valid = [t.value for t in LocationType]
            raise InvalidWorldSpecError(f"{ctx}.type {ld['type']!r} not in {valid}") from None

    agent_ids: set[str] = set()
    for i, ad in enumerate(agents):
        ctx = f"agents[{i}]"
        _require_fields(ad, ("id", "name", "occupation", "home_location_id"), ctx)
        if ad["id"] in agent_ids:
            raise InvalidWorldSpecError(f"duplicate agent id: {ad['id']!r}")
        agent_ids.add(ad["id"])
        home = ad["home_location_id"]
        if home not in loc_ids:
            raise InvalidWorldSpecError(f"{ctx}.home_location_id {home!r} not in locations")
        current = ad.get("current_location_id", home)
        if current not in loc_ids:
            raise InvalidWorldSpecError(f"{ctx}.current_location_id {current!r} not in locations")
        personality = ad.get("personality", {})
        if not isinstance(personality, dict):
            raise InvalidWorldSpecError(f"{ctx}.personality must be an object")
        for trait, value in personality.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 <= value <= 1
            ):
                raise InvalidWorldSpecError(
                    f"{ctx}.personality.{trait} must be a number in 0..1, got {value!r}"
                )


def _require_fields(d: dict, fields: tuple[str, ...], ctx: str) -> None:
    missing = [f for f in fields if f not in d]
    if missing:
        raise InvalidWorldSpecError(f"{ctx} missing required field(s): {missing}")


def _check_int_range(d: dict, key: str, lo: int, hi: int, ctx: str) -> None:
    value = d.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise InvalidWorldSpecError(f"{ctx} must be an int in {lo}..{hi}, got {value!r}")


def _is_hhmm(s: object) -> bool:
    if not isinstance(s, str) or len(s) != 5 or s[2] != ":":
        return False
    try:
        return 0 <= int(s[:2]) <= 23 and 0 <= int(s[3:]) <= 59
    except ValueError:
        return False
