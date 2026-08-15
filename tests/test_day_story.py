"""Day tracking + day-close narration (DESIGN §6.2 / M1.5).

A tick that carries the clock past midnight: rolls day+1, seals the finished
day with a narrated DayStory (one extra cognition call — 2 sampling calls for
that invoke, inside the 8-call budget), persists, and surfaces the story via
get_story / the snapshot's stories list.
"""

from __future__ import annotations

from datetime import UTC, datetime

from conftest import FakeSampling, FakeStorage

from truman_director import plugin
from truman_director.engine import tick
from truman_director.scenarios import build
from truman_director.state import MAX_STORIES, DayStory, WorldState


def _world_at(time: str, tick: int = 0) -> WorldState:
    w = build("cafe_town", datetime(2026, 8, 15, tzinfo=UTC))
    w.world_time = time
    w.current_tick = tick
    return w


def test_advance_tick_detects_midnight_rollover():
    w = _world_at("23:55")
    rolled = w.advance_tick()
    assert rolled is True
    assert w.world_time == "00:00"
    assert w.day == 2
    assert w.day_start_tick == w.current_tick


def test_advance_tick_midday_does_not_roll():
    w = _world_at("12:00")
    assert w.advance_tick() is False
    assert w.day == 1
    assert w.day_start_tick == 0


async def test_tick_across_midnight_seals_the_day():
    world = _world_at("23:55")
    sampling = FakeSampling(
        events=[{"agent_id": "alice", "action": "rest", "target": None, "reason": "睡了"}],
        story={"story": "第一天在雨声中结束。", "cliffhanger": "Bob 的窗还亮着。"},
    )
    storage = FakeStorage()

    results = await tick(world, sampling, storage, n=1)

    assert world.day == 2
    assert len(world.stories) == 1
    assert world.stories[0].day == 1
    assert world.stories[0].story == "第一天在雨声中结束。"
    assert world.stories[0].cliffhanger == "Bob 的窗还亮着。"
    # the day-close result is appended to the tick results
    assert any("day_story" in r for r in results)
    # two cognition calls: 1 decide + 1 narrate
    assert len(sampling.calls) == 2
    # story persisted in the snapshot the bundle reads
    snap = storage.data["truman:run:world"]["value"]
    assert snap["stories"][0]["day"] == 1
    assert snap["day"] == 2


async def test_day_close_respects_story_budget():
    world = _world_at("23:55")
    # drive 9 rollovers (5 min per tick, start 23:55 → 24h per 288 ticks is too
    # slow; jump the clock straight before each tick instead)
    sampling = FakeSampling()
    for day in range(MAX_STORIES + 2):
        world.world_time = "23:55"
        await tick(world, sampling, FakeStorage(), n=1)
        assert world.day == day + 2
    assert len(world.stories) == MAX_STORIES
    # MAX_STORIES+2 closed days (1..MAX_STORIES+3-1); the bound keeps the tail,
    # so the newest story is the most recently closed day.
    assert world.stories[-1].day == world.day - 1


async def test_snapshot_roundtrips_day_and_stories():
    world = _world_at("14:00", tick=42)
    world.day = 3
    world.day_start_tick = 30
    world.stories.append(DayStory(day=2, tick_from=10, tick_to=29, story="s", cliffhanger="c"))
    snap = world.snapshot()
    restored = WorldState.from_snapshot(snap)
    assert restored.day == 3
    assert restored.day_start_tick == 30
    assert restored.stories[0].story == "s"
    assert restored.stories[0].cliffhanger == "c"


def test_old_snapshot_without_day_fields_still_loads():
    """0.3.x snapshots predate day tracking — defaults land them on day 1."""
    snap = {
        "run_id": "run_old",
        "scenario": "cafe_town",
        "current_tick": 7,
        "world_time": "09:00",
        "locations": {},
        "agents": {},
        "events": [],
    }
    w = WorldState.from_snapshot(snap)
    assert w.day == 1
    assert w.day_start_tick == 0
    assert w.stories == []


async def test_get_story_action_returns_stories(monkeypatch):
    from truman_director.state import DayStory

    world = _world_at("10:00")
    world.stories = [
        DayStory(day=1, tick_from=0, tick_to=9, story="d1", cliffhanger="c1"),
        DayStory(day=2, tick_from=10, tick_to=19, story="d2", cliffhanger="c2"),
    ]
    monkeypatch.setattr(plugin, "_world", world)
    monkeypatch.setattr(plugin, "_storage", FakeStorage())

    all_stories = await plugin._tool_world(action="get_story")
    assert [s["day"] for s in all_stories["stories"]] == [1, 2]

    day2 = await plugin._tool_world(action="get_story", day=2)
    assert len(day2["stories"]) == 1
    assert day2["stories"][0]["story"] == "d2"
