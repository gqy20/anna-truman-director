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

_log = logging.getLogger("truman.storage")


async def load(storage: StorageClient) -> dict | None:
    t0 = time.monotonic()
    r = await storage.get(KEY, scope="app")
    dur = (time.monotonic() - t0) * 1000
    if not r.get("exists"):
        _log.info("load miss key=%s dur=%.0fms", KEY, dur)
        return None
    _log.info("load key=%s size=%dB dur=%.0fms", KEY, _json_size(r["value"]), dur)
    return r["value"]


async def save(storage: StorageClient, snapshot: dict) -> None:
    t0 = time.monotonic()
    await storage.set(KEY, snapshot, scope="app")
    # Size doubles as the snapshot-budget monitor (DESIGN §13.2): the APS KV
    # value ceiling is 64KB, so watch this number as memories/stories grow.
    _log.info(
        "save key=%s size=%dB dur=%.0fms", KEY, _json_size(snapshot), (time.monotonic() - t0) * 1000
    )


def _json_size(value: dict) -> int:
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
