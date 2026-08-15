"""Tick engine — the model-driven simulation loop.

The ONLY place the LLM is called. ``decide`` asks the host model what every
agent does this tick; ``tick`` advances time, applies the returned events
(plus any director injections) and persists the snapshot. No heuristics, no
fallback, no registry.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml
from executa_sdk import SamplingClient

from .errors import TickBudgetExceededError
from .state import MAX_STORIES, DayStory, WorldState, event_to_dict
from .storage import save

_log = logging.getLogger("truman.engine")

# ── decision: the single LLM call ──────────────────────────────────────

# MCP-style structured-output schema. The host enforces: serialized ≤32KB,
# depth ≤8, ≤512 nodes, name matching ^[a-zA-Z0-9_-]{1,64}$.
#
# strict:true only bites when the schema itself is strict — so every property
# is listed in `required` (OpenAI-compatible hard rule; `target` is required but
# nullable — null for `rest`, a location/agent id otherwise) and every object
# carries `additionalProperties: False` (shuts the door on hallucinated fields,
# and is what flips a backend from "valid JSON" to "conforms to schema").
DECISION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string"},
                    "action": {"enum": ["move", "rest", "work", "talk"]},
                    "target": {"type": ["string", "null"]},
                    "reason": {"type": "string"},
                },
                "required": ["agent_id", "action", "target", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["events"],
    "additionalProperties": False,
}

# Prompt copy lives in prompts.yaml — the single source for LLM-facing text,
# loaded once at import (co-located with engine.decide, the only LLM call site).
_PROMPTS_FILE = Path(__file__).parent / "prompts.yaml"

# Day-story schema (M1.5). narrate is a COGNITION call (DESIGN D1): it retells
# the day, it never decides resident actions — that remains decide's monopoly.
# Two properties, so the single-property unwrap quirk that hits DECISION_SCHEMA
# can't apply here; a non-dict parse is a loud failure (red line 4).
NARRATIVE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "story": {"type": "string"},
        "cliffhanger": {"type": "string"},
    },
    "required": ["story", "cliffhanger"],
    "additionalProperties": False,
}

# Events the narrator sees per day — bounds the prompt when a long day ran.
NARRATE_EVENT_WINDOW = 60


def _load_prompts() -> dict:
    """Load prompt texts from ``prompts.yaml``. A missing or malformed file aborts
    startup loudly — never silently fall back to a default prompt (CLAUDE.md red
    line: failures are loud)."""
    with _PROMPTS_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


_PROMPTS = _load_prompts()
SYSTEM_PROMPT: str = _PROMPTS["sampling"]["system_prompt"]
NARRATOR_PROMPT: str = _PROMPTS["sampling"]["narrator_prompt"]

MAX_TOKENS = 1024
NARRATE_MAX_TOKENS = 512  # a day story is 150-300 Chinese chars — 512 is ample
# Wall-clock cap per sampling call. Matches the sampling-summarizer reference and
# bounds how long a single tick can hang if the host stalls (SDK default is 90s).
SAMPLING_TIMEOUT = 60.0
# Each invoke gets a per-invoke sampling budget (max_calls, default 8) from the
# host. One tick = one sampling call, so n ticks inside a single invoke stay
# under budget only while n ≤ this. A larger fast-forward must be driven from the
# bundle as a loop of single-tick invokes, never as one big invoke (which would
# burn MAX_TICKS_PER_INVOKE ticks, persist them, then fail partway — a
# half-applied world). See TickBudgetExceededError.
MAX_TICKS_PER_INVOKE = 8


async def decide(sampling: SamplingClient, world_view: dict) -> list[dict]:
    """Ask the model what every agent should do this tick. Returns the raw events list."""
    payload = json.dumps(world_view, ensure_ascii=False)
    result = await sampling.create_message(
        system_prompt=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": {"type": "text", "text": payload},
            }
        ],
        max_tokens=MAX_TOKENS,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "truman_tick_decision",
                "strict": True,
                "schema": DECISION_SCHEMA,
            },
        },
        timeout=SAMPLING_TIMEOUT,
    )
    # Host returns content.text as a string — parse it ourselves. The schema
    # asks for {"events": [...]}, but some hosts unwrap the single-property
    # object and emit the bare array — accept either shape (both faithfully
    # represent "what the agents do this tick"; neither is a degraded result).
    content = result["content"]
    text = content.get("text", "") if isinstance(content, dict) else content
    data = json.loads(text)
    # Decision forensics (DESIGN §13.3): the model's choice is not reproducible,
    # so every call logs its I/O sizes and the parse path taken. The bare-array
    # shape is the known host quirk — WARNING makes its frequency observable.
    if isinstance(data, dict):
        events = data.get("events", [])
        _log.info(
            "decide tick=%s prompt=%dB resp=%dB shape=dict events=%d",
            world_view.get("current_tick"),
            len(payload.encode("utf-8")),
            len(text.encode("utf-8")) if isinstance(text, str) else -1,
            len(events),
        )
        return events
    if isinstance(data, list):
        _log.warning(
            "decide tick=%s prompt=%dB resp=%dB shape=bare_array (host unwrapped schema) events=%d",
            world_view.get("current_tick"),
            len(payload.encode("utf-8")),
            len(text.encode("utf-8")) if isinstance(text, str) else -1,
            len(data),
        )
        return data
    return []


# ── narrator: the day-close cognition call ─────────────────────────────


async def narrate(
    sampling: SamplingClient, world: WorldState, day: int, tick_from: int, tick_to: int
) -> dict:
    """Retell one finished day as prose + cliffhanger (cognition, not decision).

    The closed day's event span is passed explicitly by the caller — by the
    time day-close runs, the rollover has already moved ``day_start_tick`` to
    the new day, so the span can't be recovered from live state alone.
    """
    day_events = [event_to_dict(e) for e in world.events if tick_from <= e.tick <= tick_to][
        -NARRATE_EVENT_WINDOW:
    ]
    cast = [
        {"id": a.id, "name": a.name, "occupation": a.occupation, "goal": a.goal}
        for a in world.agents.values()
    ]
    payload = json.dumps({"day": day, "cast": cast, "events": day_events}, ensure_ascii=False)
    result = await sampling.create_message(
        system_prompt=NARRATOR_PROMPT,
        messages=[{"role": "user", "content": {"type": "text", "text": payload}}],
        max_tokens=NARRATE_MAX_TOKENS,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "truman_day_story",
                "strict": True,
                "schema": NARRATIVE_SCHEMA,
            },
        },
        timeout=SAMPLING_TIMEOUT,
    )
    content = result["content"]
    text = content.get("text", "") if isinstance(content, dict) else content
    data = json.loads(text)
    if not isinstance(data, dict) or "story" not in data:
        raise ValueError(
            f"narrate returned {type(data).__name__}, expected {{story, cliffhanger}} — "
            "host may not support two-property json_schema; refusing to guess (red line 4)"
        )
    _log.info(
        "narrate day=%s events=%dB story=%dchars cliffhanger=%dchars",
        day,
        len(payload.encode("utf-8")),
        len(data.get("story", "")),
        len(data.get("cliffhanger", "")),
    )
    return {"story": data["story"], "cliffhanger": data.get("cliffhanger", "")}


async def day_close(world: WorldState, sampling: SamplingClient, tick_from: int) -> dict:
    """Seal the finished day: narrate it, append the bounded DayStory."""
    closed_day = world.day - 1
    out = await narrate(sampling, world, closed_day, tick_from, world.current_tick)
    world.stories.append(
        DayStory(
            day=closed_day,
            tick_from=tick_from,
            tick_to=world.current_tick,
            story=out["story"],
            cliffhanger=out["cliffhanger"],
        )
    )
    if len(world.stories) > MAX_STORIES:
        del world.stories[:-MAX_STORIES]
    return out


# ── reactor: advance time, apply, persist ──────────────────────────────


async def tick(
    world: WorldState,
    sampling,  # SamplingClient
    storage,  # StorageClient
    n: int = 1,
) -> list[dict]:
    """Advance *n* ticks. Returns a list of per-tick result dicts.

    *n* is capped at :data:`MAX_TICKS_PER_INVOKE`: one tick is one sampling call,
    and the host budgets ``max_calls`` (default 8) per invoke. Asking for more is
    a loud :class:`TickBudgetExceededError` — never a silent, half-applied run
    that persists the first few ticks and then fails.
    """
    if n > MAX_TICKS_PER_INVOKE:
        raise TickBudgetExceededError(
            f"tick n={n} exceeds the per-invoke sampling budget of "
            f"{MAX_TICKS_PER_INVOKE}; drive larger fast-forwards from the bundle "
            "as a loop of single-tick invokes"
        )
    results = []
    for _ in range(n):
        prev_day_start = world.day_start_tick
        rolled = world.advance_tick()

        # Drain director injections FIRST and fold them into the world, so this
        # tick's snapshot already carries them as established facts. The model then
        # reacts in the SAME tick the director fired them — not one tick late.
        # (CLAUDE.md: injections fire at effective_tick, drained before the model decides.)
        injections = world._pending_injections[:]
        world._pending_injections.clear()
        for inj in injections:
            world.apply_event(inj)
            world.record_event(inj)
        if injections:
            _log.info(
                "tick=%s drained %d director injection(s)", world.current_tick, len(injections)
            )

        world_view = world.snapshot()
        events = await decide(sampling, world_view)
        for evt in events:
            world.apply_event(evt)
            world.record_event(evt)

        await save(storage, world.snapshot())

        # Day-close routine (DESIGN §6.2 / M1.5): the tick that carries the town
        # past midnight seals the finished day with a narrated story — the
        # model's prose retelling plus the cliffhanger that brings the director
        # back tomorrow. Budget: this invoke spent 1 decide, narrate makes it 2
        # (≤ 8 per invoke). Runs after save so the story lands in the same
        # persisted snapshot.
        if rolled:
            story = await day_close(world, sampling, prev_day_start)
            await save(storage, world.snapshot())
            results.append(
                {
                    "tick": world.current_tick,
                    "world_time": world.world_time,
                    "day": world.day,
                    "day_story": story,
                }
            )

        results.append(
            {
                "tick": world.current_tick,
                "world_time": world.world_time,
                "events": [*injections, *events],
            }
        )
    return results


def apply_inject_event(world: WorldState, event_spec: dict) -> dict:
    """Queue a director-injected event to fire at the next tick."""
    injection_id = f"inj_{uuid.uuid4().hex[:8]}"
    _log.info(
        "injection queued id=%s effective_tick=%s action=%s",
        injection_id,
        world.current_tick + 1,
        event_spec.get("action", "world_change"),
    )
    world._pending_injections.append(
        {
            "id": injection_id,
            "effective_tick": world.current_tick + 1,
            "queued_at": datetime.now(UTC).isoformat(),
            "spec": event_spec,
            **_coerce_injection(event_spec),
        }
    )
    return {
        "injection_id": injection_id,
        "effective_tick": world.current_tick + 1,
        "message": f"event queued; fires at tick {world.current_tick + 1}",
    }


def _coerce_injection(spec: dict) -> dict:
    """Normalise a director injection into a decision-event shape."""
    return {
        "agent_id": spec.get("agent_id"),
        "action": spec.get("action", "world_change"),
        "target": spec.get("target"),
        "reason": spec.get("reason", spec.get("description", "director injection")),
        "importance": spec.get("importance", 0.9),
    }
