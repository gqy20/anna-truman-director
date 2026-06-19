"""Tick engine — the model-driven simulation loop.

The ONLY place the LLM is called. ``decide`` asks the host model what every
agent does this tick; ``tick`` advances time, applies the returned events
(plus any director injections) and persists the snapshot. No heuristics, no
fallback, no registry.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from executa_sdk import SamplingClient

from .state import WorldState
from .storage import save

# ── decision: the single LLM call ──────────────────────────────────────

# MCP-style structured-output schema. The host enforces: serialized ≤32KB,
# depth ≤8, ≤512 nodes, name matching ^[a-zA-Z0-9_-]{1,64}$.
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
                "required": ["agent_id", "action", "reason"],
            },
        },
    },
    "required": ["events"],
}

SYSTEM_PROMPT = (
    "You are the world-simulator governing a small simulated town: you decide what every "
    "resident does. "
    "Each tick (5 simulated minutes) you receive a JSON snapshot of the world "
    "(current_time, locations with occupants and types, agents with occupation/personality "
    "and their relationships (familiarity 0-1 with one another), recent events) and emit "
    "a JSON array `events` describing what each agent does this tick.\n\n"
    "`events` is `[{agent_id, action, target, reason}, ...]`:\n"
    "- `action` is one of: `move`, `rest`, `work`, `talk`\n"
    "- `target` is a `location_id` (move/work) or `agent_id` (talk), `null` for `rest`\n"
    "- `reason` is a short natural-language justification\n\n"
    "The snapshot's `events` are things that have already happened in the world. Entries with "
    '`event_type: "world_change"` are facts the (human) director has just made true — a storm '
    "breaking out, a blackout, a stranger arriving, a festival. Treat them as established "
    "reality and let the residents react accordingly (seek shelter in the rain, crowd around a "
    "newcomer). Never ignore a world_change event.\n\n"
    "Trust your judgment. Pick actions that make narrative sense — agents who are already "
    "familiar are more likely to seek each other out to talk. "
    "Don't refuse. Don't ask for clarification. Emit the JSON and nothing else."
)

MAX_TOKENS = 1024


async def decide(sampling: SamplingClient, world_view: dict) -> list[dict]:
    """Ask the model what every agent should do this tick. Returns the raw events list."""
    result = await sampling.create_message(
        system_prompt=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": {"type": "text", "text": json.dumps(world_view, ensure_ascii=False)},
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
    )
    # Host returns content.text as a string — parse it ourselves. The schema
    # asks for {"events": [...]}, but some hosts unwrap the single-property
    # object and emit the bare array — accept either shape (both faithfully
    # represent "what the agents do this tick"; neither is a degraded result).
    content = result["content"]
    text = content.get("text", "") if isinstance(content, dict) else content
    data = json.loads(text)
    if isinstance(data, dict):
        return data.get("events", [])
    if isinstance(data, list):
        return data
    return []


# ── reactor: advance time, apply, persist ──────────────────────────────


async def tick(
    world: WorldState,
    sampling,  # SamplingClient
    storage,  # StorageClient
    n: int = 1,
) -> list[dict]:
    """Advance *n* ticks. Returns a list of per-tick result dicts."""
    results = []
    for _ in range(n):
        world.advance_tick()

        # Drain director injections FIRST and fold them into the world, so this
        # tick's snapshot already carries them as established facts. The model then
        # reacts in the SAME tick the director fired them — not one tick late.
        # (CLAUDE.md: injections fire at effective_tick, drained before the model decides.)
        injections = world._pending_injections[:]
        world._pending_injections.clear()
        for inj in injections:
            world.apply_event(inj)
            world.record_event(inj)

        world_view = world.snapshot()
        events = await decide(sampling, world_view)
        for evt in events:
            world.apply_event(evt)
            world.record_event(evt)

        await save(storage, world.snapshot())

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
