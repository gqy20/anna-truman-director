"""Opt-in local protocol trace. Never serialize payloads or credentials."""

import hashlib
import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

_trace = logging.getLogger("truman_protocol_trace")
_trace.propagate = False
_trace.addHandler(logging.NullHandler())
_ACTIONS = frozenset(
    [
        "init",
        "reset",
        "tick",
        "inject_event",
        "list_scenarios",
        "get_agent",
        "get_timeline",
        "get_story",
        "get_snapshot",
    ]
)
_METHODS = frozenset(["initialize", "describe", "health", "shutdown", "invoke"])


def configure() -> None:
    """Enable only when explicitly given a local diagnostic directory."""
    directory = os.environ.get("TRUMAN_TRACE_DIR")
    if not directory:
        return
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path / f"protocol-{os.getpid()}.jsonl",
        maxBytes=1_000_000,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    _trace.addHandler(handler)
    _trace.setLevel(logging.INFO)
    event("ready")


def event(stage: str, req_id=None, method=None, action=None, elapsed_ms=None) -> None:
    if not _trace.isEnabledFor(logging.INFO):
        return
    row = {"time": time.time(), "pid": os.getpid(), "stage": stage}
    if req_id is not None:
        row["request_hash"] = hashlib.sha256(str(req_id).encode("utf-8")).hexdigest()[:16]
    if method is not None:
        row["method"] = method if isinstance(method, str) and method in _METHODS else "other"
    if action is not None:
        row["action"] = action if isinstance(action, str) and action in _ACTIONS else "other"
    if elapsed_ms is not None:
        row["elapsed_ms"] = round(elapsed_ms, 1)
    _trace.info(json.dumps(row))
