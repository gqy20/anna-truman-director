"""Scenario presets — builder functions that construct initial WorldState."""

from __future__ import annotations

from datetime import datetime

from .errors import UnknownScenarioError
from .state import Agent, Location, LocationType, WorldState


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
