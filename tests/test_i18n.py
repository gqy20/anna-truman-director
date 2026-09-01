"""zh/en language switching (DESIGN §8 i18n): state fields, prompt assembly,
localized world_view projection, plugin lang plumbing, bilingual scenario data.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from conftest import FakeSampling

from truman_director import engine, plugin
from truman_director.scenarios import build, openings, scenario_infos


def _world():
    return build("cafe_town", datetime(2026, 8, 15, tzinfo=UTC))


# ── scenario data carries both languages ──────────────────────────────


def test_scenario_has_bilingual_names_goals_and_openings():
    w = _world()
    assert w.locations["loc_cafe"].name == "Bean & Bite"
    assert w.locations["loc_cafe"].name_zh == "豆香咖啡馆"
    alice = w.agents["alice"]
    assert alice.name_zh == "爱丽丝"
    assert alice.occupation_zh == "咖啡师"
    assert alice.goal and alice.goal_en  # both authored

    for o in openings():
        assert o["title"] and o["title_en"]
        assert o["event"]["reason"] and o["event_en"]["reason"]

    cafe = next(s for s in scenario_infos() if s["id"] == "cafe_town")
    assert cafe["name_zh"] == "咖啡镇" and cafe["description_zh"]


def test_snapshot_roundtrips_lang_and_bilingual_fields():
    w = _world()
    w.lang = "en"
    clone = type(w).from_snapshot(w.snapshot())
    assert clone.lang == "en"
    assert clone.locations["loc_cafe"].name_zh == "豆香咖啡馆"
    assert clone.agents["alice"].goal_en


# ── localized_view: the model sees ONE language per field ─────────────


def test_localized_view_zh_swaps_names_in():
    w = _world()
    view = engine.localized_view(w)
    assert view["locations"]["loc_cafe"]["name"] == "豆香咖啡馆"
    assert view["agents"]["alice"]["name"] == "爱丽丝"
    assert view["agents"]["alice"]["goal"] == w.agents["alice"].goal
    # the other language's fields are stripped, never leaked to the prompt
    assert "name_zh" not in view["locations"]["loc_cafe"]
    assert "goal_en" not in view["agents"]["alice"]


def test_localized_view_en_swaps_goal_in_and_keeps_names():
    w = _world()
    w.lang = "en"
    view = engine.localized_view(w)
    assert view["locations"]["loc_cafe"]["name"] == "Bean & Bite"
    assert view["agents"]["alice"]["name"] == "Alice"
    assert view["agents"]["alice"]["goal"] == w.agents["alice"].goal_en


def test_localized_view_falls_back_when_zh_missing():
    """Custom towns have no name_zh — zh view must fall back to the canonical
    name instead of dropping it."""
    w = _world()
    w.locations["loc_cafe"].name_zh = ""
    w.agents["alice"].goal_en = ""
    view = engine.localized_view(w)
    assert view["locations"]["loc_cafe"]["name"] == "Bean & Bite"
    w.lang = "en"
    view = engine.localized_view(w)
    assert view["agents"]["alice"]["goal"] == w.agents["alice"].goal


# ── prompt assembly follows lang ──────────────────────────────────────


async def test_decide_system_prompt_carries_matching_lang_rule():
    w = _world()
    sampling = FakeSampling(
        events=[{"agent_id": "alice", "action": "work", "target": None, "reason": "r"}]
    )
    await engine.decide(sampling, engine.localized_view(w))
    sys_zh = sampling.calls[0]["system_prompt"]
    assert "简体中文" in sys_zh and "English" not in sys_zh

    w.lang = "en"
    sampling2 = FakeSampling(events=[])
    await engine.decide(sampling2, engine.localized_view(w))
    sys_en = sampling2.calls[0]["system_prompt"]
    assert "English" in sys_en and "简体中文" not in sys_en


async def test_narrate_prompt_and_cast_follow_lang(monkeypatch):
    w = _world()
    w.record_event({"action": "talk", "agent_id": "alice", "target": "bob", "reason": "hi"})
    sampling = FakeSampling()

    await engine.narrate(sampling, w, day=1, tick_from=0, tick_to=1)
    call = sampling.calls[0]
    assert "简体中文" in call["system_prompt"]
    cast = json.loads(call["messages"][0]["content"]["text"])["cast"]
    assert cast[0]["name"] == "爱丽丝"
    assert cast[0]["goal"] == w.agents["alice"].goal

    w.lang = "en"
    sampling2 = FakeSampling()
    await engine.narrate(sampling2, w, day=1, tick_from=0, tick_to=1)
    call_en = sampling2.calls[0]
    assert "English prose" in call_en["system_prompt"]
    cast_en = json.loads(call_en["messages"][0]["content"]["text"])["cast"]
    assert cast_en[0]["name"] == "Alice"
    assert cast_en[0]["goal"] == w.agents["alice"].goal_en


# ── plugin plumbing: init/reset/tick accept lang ──────────────────────


async def test_init_lang_en_persists_in_snapshot(monkeypatch):
    monkeypatch.setattr(plugin, "_world", None)
    monkeypatch.setattr(plugin, "_storage", __import__("conftest").FakeStorage())

    await plugin._tool_world(action="init", scenario="cafe_town", lang="en")
    assert plugin._world.lang == "en"
    assert plugin._world.locations["loc_cafe"].name == "Bean & Bite"  # canonical intact


async def test_init_rejects_unknown_lang():
    from truman_director.errors import InvalidWorldSpecError

    try:
        await plugin._tool_world(action="init", scenario="cafe_town", lang="fr")
    except InvalidWorldSpecError:
        pass
    else:
        raise AssertionError("lang='fr' must be rejected loudly")


async def test_tick_switches_lang_mid_run(monkeypatch):
    from conftest import FakeStorage

    monkeypatch.setattr(plugin, "_world", _world())
    storage = FakeStorage()
    monkeypatch.setattr(plugin, "_storage", storage)
    monkeypatch.setattr(plugin, "_sampling", FakeSampling(events=[]))

    await plugin._tool_world(action="tick", n=1, lang="en")
    assert plugin._world.lang == "en"
    assert storage.data["truman:run:world"]["value"]["lang"] == "en"


async def test_get_agent_returns_bilingual_fields(monkeypatch):
    from conftest import FakeStorage

    monkeypatch.setattr(plugin, "_world", _world())
    monkeypatch.setattr(plugin, "_storage", FakeStorage())
    out = await plugin._tool_world(action="get_agent", agent_id="alice")
    a = out["agent"]
    assert a["name"] == "Alice" and a["name_zh"] == "爱丽丝"
    assert a["goal_en"]
    assert out["location"]["name_zh"] == "爱丽丝的公寓"
