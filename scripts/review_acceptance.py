"""Deterministic Marketplace TC-01..TC-05 and security acceptance runner.

Spawns the real stdio plugin, services reverse RPCs with deterministic model
responses, preserves the APS-like KV dictionary across a plugin restart, and
prints evidence that can be attached to a Marketplace resubmission.
"""

from __future__ import annotations

import json

from local_e2e import Host, _configure_console_utf8

WORLD_KEY = "truman:run:world"
XSS_PAYLOAD = '<img src=x onerror="window.__qa_xss=1">'


class ReviewHost(Host):
    def __init__(self, shared_kv: dict | None = None):
        super().__init__()
        if shared_kv is not None:
            self.kv = shared_kv
        self.decision_count = 0

    def _sampling(self, params: dict) -> dict:
        name = (params.get("responseFormat") or {}).get("json_schema", {}).get("name")
        if name == "truman_day_story":
            payload = {
                "story": "The grant changed Alice's plans and drew Bob into the cafe's future.",
                "cliffhanger": "Will they spend it together?",
            }
        else:
            self.decision_count += 1
            payload = {
                "events": [
                    {
                        "agent_id": "alice",
                        "action": "talk",
                        "target": "bob",
                        "reason": f"Alice discusses the director event with Bob (step {self.decision_count}).",
                    },
                    {
                        "agent_id": "bob",
                        "action": "work",
                        "target": None,
                        "reason": "Bob writes down how the event could affect the town.",
                    },
                    {
                        "agent_id": "truman",
                        "action": "rest",
                        "target": None,
                        "reason": "Truman watches the consequences unfold.",
                    },
                ]
            }
        return {
            "role": "assistant",
            "content": {"type": "text", "text": json.dumps(payload, ensure_ascii=False)},
            "model": "review-deterministic",
            "stopReason": "endTurn",
        }


def _initialize(host: ReviewHost) -> None:
    init = host.request("initialize", {"protocolVersion": "2.0"})
    assert init["client_capabilities"]["sampling"] == {}
    assert host.request("describe")["tools"][0]["name"] == "world"


def _expect_rpc_error(host: ReviewHost, args: dict, code: int) -> None:
    try:
        host.invoke_world(args)
    except RuntimeError as exc:
        assert f"'code': {code}" in str(exc), exc
    else:
        raise AssertionError(f"expected RPC error {code}: {args}")


def main() -> None:
    host = ReviewHost()
    restarted: ReviewHost | None = None
    try:
        _initialize(host)
        host.invoke_world({"action": "init", "scenario": "cafe_town", "lang": "en"})

        alice = host.invoke_world({"action": "get_agent", "agent_id": "alice"})
        assert alice["agent"]["name"] == "Alice"
        print("TC-01 PASS — current town and resident dossier are readable")

        host.invoke_world({"action": "tick", "n": 1, "lang": "en"})
        alice = host.invoke_world({"action": "get_agent", "agent_id": "alice"})
        assert alice["relationships"][0]["agent_id"] == "bob"
        print("TC-02 PASS — autonomous interaction changed Alice↔Bob relationship state")

        host.invoke_world(
            {
                "action": "inject_event",
                "event": {
                    "reason": "A sudden rainstorm floods the town square.",
                    "importance": 0.95,
                },
            }
        )
        host.invoke_world({"action": "tick", "n": 1, "lang": "en"})
        timeline = host.invoke_world({"action": "get_timeline", "event_type": "world_change"})
        assert any("rainstorm" in e["description"] for e in timeline["events"])
        print("TC-03 PASS — town-wide event entered the shared world and persisted")

        host.invoke_world(
            {
                "action": "inject_event",
                "event": {
                    "agent_id": "alice",
                    "action": "world_change",
                    "reason": "Alice receives an unexpected 500 yuan opportunity grant.",
                    "importance": 0.95,
                },
            }
        )
        host.invoke_world({"action": "tick", "n": 1, "lang": "en"})
        alice = host.invoke_world({"action": "get_agent", "agent_id": "alice"})
        assert any("500 yuan" in e["description"] for e in alice["recent_events"])
        print("TC-04 PASS — individual intervention is attributed to Alice and visible downstream")

        for _ in range(2):
            host.invoke_world({"action": "tick", "n": 1, "lang": "en"})
        shared_kv = host.kv
        before = shared_kv[WORLD_KEY]
        run_id = before["run_id"]
        familiarity = before["agents"]["alice"]["relationships"]["bob"]["familiarity"]
        host.close()

        restarted = ReviewHost(shared_kv)
        _initialize(restarted)
        restored = restarted.invoke_world({"action": "get_agent", "agent_id": "alice"})
        assert shared_kv[WORLD_KEY]["run_id"] == run_id
        restored_bob = next(r for r in restored["relationships"] if r["agent_id"] == "bob")
        assert restored_bob["familiarity"] == familiarity
        assert any("500 yuan" in e["description"] for e in restored["recent_events"])
        restarted.invoke_world({"action": "tick", "n": 1, "lang": "en"})
        assert shared_kv[WORLD_KEY]["current_tick"] == before["current_tick"] + 1
        print("TC-05 PASS — consequences survived plugin restart and evolution continued")

        _expect_rpc_error(
            restarted,
            {"action": "inject_event", "event": {"action": "teleport", "reason": "invalid"}},
            -32006,
        )
        _expect_rpc_error(
            restarted,
            {
                "action": "inject_event",
                "event": {"agent_id": "nobody", "reason": "invalid resident"},
            },
            -32005,
        )
        restarted.invoke_world(
            {"action": "inject_event", "event": {"reason": XSS_PAYLOAD, "importance": 0.9}}
        )
        restarted.invoke_world({"action": "tick", "n": 1, "lang": "en"})
        assert any(
            XSS_PAYLOAD in e["description"]
            for e in restarted.invoke_world({"action": "get_timeline"})["events"]
        )
        print("SECURITY PASS — invalid events fail loudly; markup remains inert event data")
        print("\nMarketplace acceptance complete: TC-01..TC-05 + security PASS")
    finally:
        if restarted is not None:
            restarted.close()
        elif host.proc.poll() is None:
            host.close()


if __name__ == "__main__":
    _configure_console_utf8()
    main()
