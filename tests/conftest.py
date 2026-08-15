"""Shared test fixtures: async fakes for the reverse-RPC clients."""

from __future__ import annotations

import json


class FakeSampling:
    """Stand-in for SamplingClient. Dispatches on the response_format schema
    name: ``truman_tick_decision`` → canned decide events; ``truman_day_story``
    → canned day story. Any other name raises (unknown cognition call)."""

    def __init__(self, events: list[dict] | None = None, story: dict | None = None):
        self.events = events or []
        self.story = story or {
            "story": "小镇度过了平静的一天。",
            "cliffhanger": "夜色里,谁家的灯还亮着。",
        }
        self.calls: list[dict] = []

    async def create_message(self, *, messages, max_tokens, **kwargs):
        self.calls.append({"messages": messages, "max_tokens": max_tokens, **kwargs})
        name = (kwargs.get("response_format") or {}).get("json_schema", {}).get("name")
        if name == "truman_day_story":
            text = json.dumps(self.story, ensure_ascii=False)
        else:
            text = json.dumps({"events": self.events})
        return {"content": {"type": "text", "text": text}}


class FakeStorage:
    """In-memory StorageClient: get/set/delete/list, async."""

    def __init__(self):
        self.data: dict[str, dict] = {}

    async def get(self, key, *, scope="app", **kwargs):
        rec = self.data.get(key)
        if rec is None:
            return {"value": None, "exists": False, "etag": None}
        return {"value": rec["value"], "exists": True, "etag": rec.get("etag")}

    async def set(self, key, value, *, scope="app", **kwargs):
        self.data[key] = {"value": value, "etag": "etag-1"}
        return {"etag": "etag-1", "generation": 1, "size_bytes": 0}

    async def delete(self, key, *, scope="app", **kwargs):
        self.data.pop(key, None)
        return {"deleted": True}

    async def list(self, *, prefix=None, **kwargs):
        keys = [k for k in self.data if prefix is None or k.startswith(prefix)]
        return {"items": [{"key": k} for k in keys], "next_cursor": None}
