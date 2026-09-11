"""APS KV persistence — single key, fail loud.

``storage.set`` raises :class:`StorageError` on failure; we let it propagate
so the host sees the error rather than silently losing the world snapshot.
"""

from __future__ import annotations

import json
import logging
import time

from executa_sdk import StorageClient

KEY = "truman:run:world"
SCOPE = "tool"  # Plugin tokens cannot access App-side scope="app".

_log = logging.getLogger("truman.storage")


async def load(storage: StorageClient) -> dict | None:
    t0 = time.monotonic()
    r = await storage.get(KEY, scope=SCOPE)
    dur = (time.monotonic() - t0) * 1000
    # Production APS always answers {value, exists}; the dev harness legacy
    # backend omits `exists` entirely (anna_app_core dispatcher `_h_storage_get`
    # returns bare {value}). A snapshot is always a dict, so a non-None value
    # is an unambiguous hit under either shape.
    value = r.get("value")
    if not r.get("exists") and value is None:
        _log.info("load miss key=%s dur=%.0fms", KEY, dur)
        return None
    _log.info("load key=%s size=%dB dur=%.0fms", KEY, _json_size(value), dur)
    return value


async def save(storage: StorageClient, snapshot: dict) -> None:
    t0 = time.monotonic()
    await storage.set(KEY, snapshot, scope=SCOPE)
    # Size doubles as the snapshot-budget monitor (DESIGN §13.2): the APS KV
    # value ceiling is 64KB, so watch this number as memories/stories grow.
    _log.info(
        "save key=%s size=%dB dur=%.0fms", KEY, _json_size(snapshot), (time.monotonic() - t0) * 1000
    )


def _json_size(value: dict) -> int:
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
