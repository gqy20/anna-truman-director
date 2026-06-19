"""APS KV persistence — single key, fail loud.

``storage.set`` raises :class:`StorageError` on failure; we let it propagate
so the host sees the error rather than silently losing the world snapshot.
"""

from __future__ import annotations

from executa_sdk import StorageClient

KEY = "truman:run:world"


async def load(storage: StorageClient) -> dict | None:
    r = await storage.get(KEY, scope="app")
    return r["value"] if r.get("exists") else None


async def save(storage: StorageClient, snapshot: dict) -> None:
    await storage.set(KEY, snapshot, scope="app")
