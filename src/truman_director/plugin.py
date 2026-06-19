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
import json
import sys
import threading
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
from .errors import InvalidWorldSpecError, TrumanError, WorldNotInitializedError
from .scenarios import build, build_from_spec
from .state import WorldState
from .storage import save

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
                "init | tick | inject_event."
            ),
            "parameters": [
                {"name": "action", "type": "string", "required": True},
                {"name": "scenario", "type": "string", "required": False},
                {"name": "spec", "type": "object", "required": False},
                {"name": "n", "type": "integer", "required": False},
                {"name": "event", "type": "object", "required": False},
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


async def _tool_world(action: str, **kwargs: Any) -> dict:
    global _world

    if action == "init":
        spec = kwargs.get("spec")
        scenario = kwargs.get("scenario")
        if spec:
            world = build_from_spec(spec, datetime.now(UTC))
        elif scenario:
            world = build(scenario, datetime.now(UTC))
        else:
            raise InvalidWorldSpecError("init requires 'scenario' (preset) or 'spec' (custom)")
        # Seed occupants from each agent's starting location.
        for agent in world.agents.values():
            loc = world.locations.get(agent.current_location_id)
            if loc:
                loc.occupants.add(agent.id)
        await save(_storage, world.snapshot())
        _world = world
        return {"scenario": world.scenario, "tick": 0, "world_time": world.world_time}

    if _world is None:
        raise WorldNotInitializedError("call action='init' first")

    if action == "tick":
        n = kwargs.get("n", 1)
        return {"results": await tick(_world, _sampling, _storage, n)}

    if action == "inject_event":
        return apply_inject_event(_world, kwargs["event"])

    raise ValueError(f"unknown action: {action!r}")


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
    try:
        data = await _tool_world(**args)
        # Host's InvokeResult.from_dict reads result["success"] (default False)
        # and result["data"] — the payload MUST be wrapped this way.
        _ok(req_id, {"success": True, "tool": tool, "data": data})
    except (StorageError, SamplingError) as exc:
        _err(req_id, exc.code, exc.message, getattr(exc, "data", None))
    except TrumanError as exc:  # business error: surface its declared code (-32001/-32002/-32003)
        _err(req_id, exc.code, str(exc))
    except Exception as exc:  # protocol framing: surface as a JSON-RPC error response
        _err(req_id, -32000, f"{type(exc).__name__}: {exc}")


def _handle_initialize(req_id: Any, params: dict) -> None:
    # Negotiate the host's protocol version. Sampling requires v2; on a v1 host
    # we disable sampling in-process so any tick surfaces a loud SamplingError
    # instead of hanging or silently degrading (CLAUDE.md red line 4).
    proto = (params or {}).get("protocolVersion") or PROTOCOL_VERSION_V1
    if proto != PROTOCOL_VERSION_V2:
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


def main() -> None:
    print(f"[truman-director] v{__version__} ready", file=sys.stderr)
    asyncio.run(_main())


if __name__ == "__main__":
    main()
