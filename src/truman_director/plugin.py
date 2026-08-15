#!/usr/bin/env python3
"""truman-director — Executa stdio tool plugin.

One tool ``world`` with an ``action`` discriminator: init | tick | inject_event.
All agent decisions come from the host LLM via SamplingClient (reverse RPC).
World state persists to APS KV (reverse RPC) under a single key.

Protocol: JSON-RPC 2.0 over stdio. Threading model mirrors the executa_sdk
storage-notebook reference: the asyncio loop runs in the main thread; a daemon
thread reads stdin; host ``invoke`` requests are scheduled onto the loop via
``run_coroutine_threadsafe``; responses to OUR reverse-RPC calls are routed
back through ``make_response_router``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sys
import threading
import time
from datetime import UTC, datetime
from typing import Any

from executa_sdk import (
    PROTOCOL_VERSION_V1,
    PROTOCOL_VERSION_V2,
    SamplingClient,
    SamplingError,
    StorageClient,
    StorageError,
    make_response_router,
)

from . import __version__
from .engine import apply_inject_event, tick
from .errors import (
    AgentNotFoundError,
    InvalidWorldSpecError,
    TrumanError,
    WorldNotInitializedError,
)
from .scenarios import build, build_from_spec, scenario_infos
from .state import WorldState, event_to_dict
from .storage import load, save

_log = logging.getLogger("truman.plugin")

MANIFEST: dict[str, Any] = {
    "display_name": "Truman Director",
    "version": __version__,
    "description": "LLM-directed tick-based town simulator.",
    "author": "Anna Hackathon Team",
    "license": "MIT",
    "tags": ["simulation", "social", "director"],
    "host_capabilities": ["aps.kv", "aps.scope.app.read", "aps.scope.app.write", "llm.sample"],
    "tools": [
        {
            "name": "world",
            "description": (
                "Manage the Truman Town simulation. Use 'action' to select: "
                "init | reset | tick | inject_event | list_scenarios | "
                "get_agent | get_timeline."
            ),
            "parameters": [
                {"name": "action", "type": "string", "required": True},
                {"name": "scenario", "type": "string", "required": False},
                {"name": "spec", "type": "object", "required": False},
                {"name": "n", "type": "integer", "required": False},
                {"name": "event", "type": "object", "required": False},
                {"name": "agent_id", "type": "string", "required": False},
                {"name": "limit", "type": "integer", "required": False},
                {"name": "event_type", "type": "string", "required": False},
            ],
        }
    ],
    "runtime": {"type": "uv", "min_version": "0.1.0"},
}

# Reverse-RPC clients. Constructed bare: the SDK default write_frame serialises
# each frame to stdout. We share the single stdin reader across both via the
# response router.
_sampling = SamplingClient()
_storage = StorageClient()
_route_response = make_response_router(_sampling, _storage)

# The live simulation run. Module-level because invoke requests arrive on the
# asyncio loop from the stdin thread — there is no caller to thread it through.
_world: WorldState | None = None

# Bound in _main() once the asyncio loop is running.
_loop: asyncio.AbstractEventLoop | None = None
_stop: asyncio.Event | None = None


# ─── world tool (single dispatcher) ────────────────────────────────────


async def _require_world() -> WorldState:
    """Live-world actions (tick / inject / queries) land here. The plugin is a
    long-lived stdio child of the Matrix Agent — an Agent restart / redeploy /
    crash reboots this process and loses the module-level _world. The snapshot
    in APS KV is the single source of truth (CLAUDE.md red line 2), so on first
    access we restore _world from it instead of forcing the user to re-init. A
    missing snapshot is the only genuinely-uninitialized case → loud error. A
    storage call failure propagates as StorageError (red line 4 — never silent).
    """
    global _world
    if _world is None:
        snapshot = await load(_storage)
        if snapshot is None:
            raise WorldNotInitializedError("call action='init' first")
        _world = WorldState.from_snapshot(snapshot)
        _log.info("world restored from APS KV (run=%s tick=%s)", _world.run_id, _world.current_tick)
    return _world


def _build_world(kwargs: dict[str, Any]) -> WorldState:
    """init / reset share the construction path — both mint a fresh run_id."""
    spec = kwargs.get("spec")
    scenario = kwargs.get("scenario")
    if spec:
        return build_from_spec(spec, datetime.now(UTC))
    if scenario:
        return build(scenario, datetime.now(UTC))
    raise InvalidWorldSpecError("init/reset requires 'scenario' (preset) or 'spec' (custom)")


def _agent_detail(world: WorldState, agent_id: str) -> dict:
    """Full resident dossier for get_agent: identity, whereabouts, relationships
    with names resolved, and the events they were part of (L1 UI / Anna chat)."""
    agent = world.agents.get(agent_id)
    if agent is None:
        raise AgentNotFoundError(
            f"unknown agent_id: {agent_id!r}; residents: {sorted(world.agents)}"
        )
    loc = world.locations.get(agent.current_location_id)
    home = world.locations.get(agent.home_location_id)
    relationships = [
        {
            "agent_id": rid,
            "name": world.agents[rid].name if rid in world.agents else rid,
            "familiarity": rel.familiarity,
            "trust": rel.trust,
            "affinity": rel.affinity,
            "last_interaction_tick": rel.last_interaction_tick,
        }
        for rid, rel in sorted(agent.relationships.items())
    ]
    involved = [
        event_to_dict(e)
        for e in world.events
        if e.actor_agent_id == agent_id or e.target_agent_id == agent_id
    ]
    return {
        "agent": {
            "id": agent.id,
            "name": agent.name,
            "occupation": agent.occupation,
            "goal": agent.goal,
            "personality": agent.personality,
            "current_activity": agent.current_activity,
        },
        "location": {"id": loc.id, "name": loc.name} if loc else None,
        "home": {"id": home.id, "name": home.name} if home else None,
        "relationships": relationships,
        "recent_events": involved[-10:],
    }


def _timeline(world: WorldState, kwargs: dict[str, Any]) -> dict:
    """get_timeline: filtered tail of the in-memory event list (bounded 500)."""
    limit = max(1, min(100, int(kwargs.get("limit", 30))))
    agent_id = kwargs.get("agent_id")
    event_type = kwargs.get("event_type")
    events = world.events
    if agent_id:
        events = [
            e for e in events if e.actor_agent_id == agent_id or e.target_agent_id == agent_id
        ]
    if event_type:
        events = [e for e in events if e.event_type == event_type]
    return {"events": [event_to_dict(e) for e in events[-limit:]]}


async def _tool_world(action: str, **kwargs: Any) -> dict:
    global _world

    if action in ("init", "reset"):
        # reset is init with intent: fresh run_id, the old snapshot is simply
        # overwritten by the first save below.
        world = _build_world(kwargs)
        for agent in world.agents.values():
            loc = world.locations.get(agent.current_location_id)
            if loc:
                loc.occupants.add(agent.id)
        await save(_storage, world.snapshot())
        _world = world
        return {"scenario": world.scenario, "tick": 0, "world_time": world.world_time}

    if action == "list_scenarios":
        return {"scenarios": scenario_infos()}

    if action not in ("tick", "inject_event", "get_agent", "get_timeline"):
        raise ValueError(f"unknown action: {action!r}")

    world = await _require_world()

    if action == "tick":
        n = kwargs.get("n", 1)
        return {"results": await tick(world, _sampling, _storage, n)}

    if action == "inject_event":
        return apply_inject_event(world, kwargs["event"])

    if action == "get_agent":
        return _agent_detail(world, kwargs["agent_id"])

    return _timeline(world, kwargs)


# ─── JSON-RPC framing ─────────────────────────────────────────────────


def _write(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _ok(req_id: Any, result: dict) -> None:
    _write({"jsonrpc": "2.0", "id": req_id, "result": result})


def _err(req_id: Any, code: int, message: str, data: dict | None = None) -> None:
    err: dict = {"code": code, "message": message}
    if data:
        err["data"] = data
    _write({"jsonrpc": "2.0", "id": req_id, "error": err})


# ─── method handlers ──────────────────────────────────────────────────


async def _handle_invoke(req_id: Any, params: dict) -> None:
    tool = params.get("tool")
    args = params.get("arguments") or {}
    if tool != "world":
        _err(req_id, -32601, f"unknown tool: {tool!r}")
        return
    # Observability (DESIGN §13.2): every invoke logged in/out with duration.
    # Args are logged as keys only — a custom spec can be large and is not
    # something the log needs verbatim.
    action = args.get("action")
    t0 = time.monotonic()
    _log.info("invoke start action=%s args=%s", action, sorted(args))
    try:
        data = await _tool_world(**args)
        # Host's InvokeResult.from_dict reads result["success"] (default False)
        # and result["data"] — the payload MUST be wrapped this way.
        _ok(req_id, {"success": True, "tool": tool, "data": data})
        _log.info("invoke ok action=%s dur=%.0fms", action, (time.monotonic() - t0) * 1000)
    except (StorageError, SamplingError) as exc:
        _err(req_id, exc.code, exc.message, getattr(exc, "data", None))
        _log.error(
            "invoke fail action=%s code=%s dur=%.0fms",
            action,
            exc.code,
            (time.monotonic() - t0) * 1000,
        )
    except TrumanError as exc:  # business error: surface its declared code (-32001/-32002/-32003)
        _err(req_id, exc.code, str(exc))
        _log.error(
            "invoke fail action=%s code=%s dur=%.0fms",
            action,
            exc.code,
            (time.monotonic() - t0) * 1000,
        )
    except Exception as exc:  # protocol framing: surface as a JSON-RPC error response
        _err(req_id, -32000, f"{type(exc).__name__}: {exc}")
        _log.exception("invoke fail action=%s dur=%.0fms", action, (time.monotonic() - t0) * 1000)


def _handle_initialize(req_id: Any, params: dict) -> None:
    # Negotiate the host's protocol version. Sampling requires v2; on a v1 host
    # we disable sampling in-process so any tick surfaces a loud SamplingError
    # instead of hanging or silently degrading (CLAUDE.md red line 4).
    proto = (params or {}).get("protocolVersion") or PROTOCOL_VERSION_V1
    if proto != PROTOCOL_VERSION_V2:
        _log.warning("host offered protocolVersion=%s — sampling disabled in-process", proto)
        _sampling.disable(
            f"host offered protocolVersion={proto!r}; "
            "sampling/createMessage requires Executa protocol 2.0"
        )
    _ok(
        req_id,
        {
            "protocolVersion": PROTOCOL_VERSION_V2 if proto == PROTOCOL_VERSION_V2 else proto,
            "serverInfo": {
                "name": MANIFEST["display_name"],
                "version": MANIFEST["version"],
            },
            # client_capabilities declares what WE will use as a reverse-RPC
            # originator. Without client_capabilities.sampling the host's Nexus
            # gate ignores sampling/createMessage → engine.decide()'s await hangs
            # to the SDK timeout (the "Matrix Agent never came back" symptom on
            # the platform). storage.kv is declared too — we persist via storage/*.
            "client_capabilities": (
                {"sampling": {}, "storage": {"kv": True}} if proto == PROTOCOL_VERSION_V2 else {}
            ),
            # capabilities is the server-side capability notice (informational).
            "capabilities": {
                "storage": {"kv": True, "files": True},
                "sampling": {"enabled": True},
            },
        },
    )


# ─── stdio loop (runs in a daemon thread) ─────────────────────────────


def _stdin_loop() -> None:
    try:
        for raw in sys.stdin:
            raw = raw.strip()
            if not raw:
                continue
            msg = json.loads(raw)
            # Responses to OUR reverse-RPC requests are routed first.
            if "method" not in msg and _route_response(msg):
                continue
            method = msg.get("method")
            req_id = msg.get("id")
            params = msg.get("params") or {}
            if method == "initialize":
                _handle_initialize(req_id, params)
            elif method == "describe":
                # result MUST be the manifest itself — host reads data["name"].
                _ok(req_id, MANIFEST)
            elif method == "health":
                _ok(req_id, {"status": "ok", "version": __version__})
            elif method == "shutdown":
                _ok(req_id, {})
                return
            elif method == "invoke":
                assert _loop is not None
                asyncio.run_coroutine_threadsafe(_handle_invoke(req_id, params), _loop)
            else:
                _err(req_id, -32601, f"method not found: {method}")
    finally:
        # stdin closed (parent went away) — unblock _main() so we exit cleanly.
        if _loop is not None and _stop is not None:
            _loop.call_soon_threadsafe(_stop.set)


async def _main() -> None:
    global _loop, _stop
    _loop = asyncio.get_running_loop()
    _stop = asyncio.Event()
    threading.Thread(target=_stdin_loop, daemon=True).start()
    await _stop.wait()


def _configure_logging() -> None:
    """stderr-only logging (DESIGN §13.1). stdout is the JSON-RPC channel — any
    human-readable output there corrupts the protocol stream (official pitfall
    #3), so the sole handler writes to stderr. Level via TRUMAN_LOG_LEVEL
    (INFO in production, DEBUG when diagnosing). Windows consoles default to a
    legacy code page — force UTF-8 so log lines with Chinese text can't crash
    the stream writer."""
    if sys.stderr.encoding and sys.stderr.encoding.lower().replace("-", "") != "utf8":
        with contextlib.suppress(AttributeError, OSError):  # non-reconfigurable stream
            sys.stderr.reconfigure(encoding="utf-8")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S")
    )
    root = logging.getLogger("truman")
    root.setLevel(os.environ.get("TRUMAN_LOG_LEVEL", "INFO").upper())
    root.addHandler(handler)
    root.propagate = False


def main() -> None:
    _configure_logging()
    _log.info("ready v%s", __version__)
    asyncio.run(_main())


if __name__ == "__main__":
    main()
