#!/usr/bin/env python3
"""Local real-host E2E driver — real plugin + real LLM, no browser.

The dev-harness bundle path needs interactive UI clicks, which automated
sandboxes often can't deliver into iframes. This driver plays the HOST side of
the Executa protocol directly over stdio:

  * initialize (v2, with client_capabilities) / describe / invoke
  * reverse RPC ``storage/*``  → in-memory KV (same semantics as legacy backend)
  * reverse RPC ``sampling/createMessage`` → proxied to the real staging LLM
    through the CLI's documented dev path (``anna-app login`` PAT →
    ``/api/v1/anna-apps/dev/session/mint`` → ``/api/v1/copilot/app/complete``;
    see @anna-ai/cli dist/sampling-*.js SamplingBridge).

Run:  uv run python scripts/local_e2e.py
Needs: ~/.config/anna/credentials.json with a valid PAT (anna-app login).
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time

HOST = "https://anna.partners"
APP_SLUG = "anna-truman-director"

# MOCK=1 → answer sampling reverse-RPCs with canned decide/narrate payloads.
# Use when the account's dev sampling quota is unavailable (APP_QUOTA_EXCEEDED)
# to still verify the full protocol chain: tick → day rollover → narrate →
# story in snapshot → get_story. Real-LLM quality checks need MOCK unset.
MOCK = os.environ.get("MOCK") == "1"

# This dev box routes egress through a local proxy (WinHTTP 127.0.0.1:7890).
# Python's urllib ignores WinHTTP settings, so try direct first and fall back
# to the local proxy on TLS/connection failure.
_LOCAL_PROXY = os.environ.get("ANNA_E2E_PROXY", "http://127.0.0.1:7890")


def _http_post_json(url: str, body: dict, headers: dict, timeout: int = 60) -> dict:
    """POST via a Node child process: the platform API sits behind Cloudflare,
    which rejects urllib/curl TLS fingerprints (error 1010) but accepts the
    Node/undici fingerprint the official CLI bridge itself uses."""
    payload = json.dumps(
        {
            "url": url,
            "headers": {"content-type": "application/json", **headers},
            "body": json.dumps(body, ensure_ascii=False),
        }
    )
    script = (
        "const r = JSON.parse(process.argv[1]);"
        "fetch(r.url, {method:'POST', headers:r.headers, body:r.body})"
        ".then(async s => { const t = await s.text();"
        " process.stdout.write(JSON.stringify({status: s.status, body: t})); })"
        ".catch(e => { process.stdout.write(JSON.stringify({status: 0, body: String(e)})); });"
    )
    out = subprocess.run(
        ["node", "-e", script, "--", payload],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    try:
        res = json.loads(out.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"node fetch failed: {out.stderr[:300]}") from None
    if res["status"] >= 400:
        raise RuntimeError(f"HTTP {res['status']} from {url}: {res['body'][:200]!r}")
    return json.loads(res["body"])


# Custom spec starting at 23:50 — tick 2 crosses midnight, so a short run
# exercises the full day-close routine (decide + narrate) with the real LLM.
SPEC = {
    "name": "e2e_midnight_town",
    "world_time": "23:50",
    "locations": [
        {"id": "loc_cafe", "name": "Night Cafe", "type": "cafe", "x": 50, "y": 40},
        {"id": "loc_home_a", "name": "Alice's Home", "type": "home", "x": 20, "y": 70},
        {"id": "loc_home_b", "name": "Bob's Home", "type": "home", "x": 80, "y": 70},
    ],
    "agents": [
        {
            "id": "alice",
            "name": "Alice",
            "occupation": "Barista",
            "home_location_id": "loc_home_a",
            "goal": "失眠,想知道 Bob 今晚为什么还没回家。",
        },
        {
            "id": "bob",
            "name": "Bob",
            "occupation": "Writer",
            "home_location_id": "loc_home_b",
            "goal": "赶稿到深夜,灵感却来自隔壁咖啡馆的灯光。",
        },
    ],
}


class Host:
    def __init__(self):
        env = {**os.environ, "PYTHONPATH": "src", "TRUMAN_LOG_LEVEL": "INFO"}
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "truman_director.plugin"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        self.seq = 0
        self.kv: dict = {}

    # ── protocol plumbing ────────────────────────────────────────────

    def _write(self, msg: dict) -> None:
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: dict | None = None) -> dict:
        """Send a request, servicing the plugin's reverse-RPCs until the
        matching response arrives (plugin only calls back while an invoke is
        in flight, so a sequential read loop is sufficient)."""
        self.seq += 1
        rid = self.seq
        self._write({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        while True:
            line = self.proc.stdout.readline()
            if not line:
                err = self.proc.stderr.read()
                raise RuntimeError(f"plugin stdout closed. stderr:\n{err}")
            msg = json.loads(line)
            if "method" in msg:
                self._handle_reverse(msg)
                continue
            if msg.get("id") == rid:
                if "error" in msg:
                    raise RuntimeError(f"{method} failed: {msg['error']}")
                return msg["result"]
            # response to an already-served reverse request — ignore

    def _handle_reverse(self, msg: dict) -> None:
        method, rid, params = msg["method"], msg.get("id"), msg.get("params") or {}
        try:
            if method == "storage/get":
                key = params["key"]
                rec = self.kv.get(key)
                result = (
                    {"value": rec, "exists": True, "etag": "e1"}
                    if rec is not None
                    else {"value": None, "exists": False, "etag": None}
                )
            elif method == "storage/set":
                self.kv[params["key"]] = params["value"]
                result = {"ok": True, "etag": "e1"}
            elif method == "sampling/createMessage":
                result = self._sampling(params)
            else:
                raise RuntimeError(f"unhandled reverse method {method!r}")
            self._write({"jsonrpc": "2.0", "id": rid, "result": result})
        except Exception as exc:  # loud: surface into the plugin as RPC error
            self._write(
                {"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": str(exc)}}
            )

    # ── real sampling (mirrors @anna-ai/cli SamplingBridge.realMessage) ──

    _token: str | None = None
    _token_exp: float = 0.0

    def _mint(self) -> str:
        if self._token and self._token_exp - 30 > time.time():
            return self._token
        out = _http_post_json(
            f"{HOST}/api/v1/anna-apps/dev/session/mint",
            {"pat": _load_pat(), "kind": "complete", "app_slug": APP_SLUG},
            headers={},
            timeout=30,
        )
        self._token = out["app_session_token"]
        self._token_exp = time.time() + out.get("expires_in", 600)
        print(f"  [host] sampling session minted (expires in {out.get('expires_in')}s)")
        return self._token

    def _sampling(self, params: dict) -> dict:
        if MOCK:
            name = (params.get("responseFormat") or {}).get("json_schema", {}).get("name")
            if name == "truman_day_story":
                text = json.dumps(
                    {
                        "story": "夜色收拢了小镇。Alice 的灯和 Bob 的灯隔着两条街遥遥相望,",
                        "cliffhanger": "Bob 的窗户在午夜后依然亮着,他在等谁?",
                    },
                    ensure_ascii=False,
                )
            else:
                text = json.dumps(
                    {
                        "events": [
                            {
                                "agent_id": "alice",
                                "action": "move",
                                "target": "loc_cafe",
                                "reason": "睡不着,想去看看咖啡馆的灯还亮不亮。",
                            },
                            {
                                "agent_id": "bob",
                                "action": "work",
                                "target": None,
                                "reason": "赶稿到深夜,灵感来自隔壁的灯光。",
                            },
                        ]
                    },
                    ensure_ascii=False,
                )
            return {
                "role": "assistant",
                "content": {"type": "text", "text": text},
                "model": "mock",
                "stopReason": "endTurn",
            }
        body: dict = {
            "messages": [
                {"role": m["role"], "content": _content_text(m["content"])}
                for m in params.get("messages", [])
            ],
            "max_tokens": params.get("maxTokens", 1024),
        }
        if params.get("systemPrompt"):
            body["system"] = params["systemPrompt"]
        if params.get("responseFormat"):
            body["response_format"] = params["responseFormat"]
        raw = _http_post_json(
            f"{HOST}/api/v1/copilot/app/complete",
            body,
            headers={"authorization": f"Bearer {self._mint()}"},
            timeout=90,
        )
        # normalise (same coercion as the CLI bridge)
        if raw.get("role") == "assistant" and isinstance(raw.get("content"), dict):
            return raw
        text = (
            raw.get("text")
            or (raw.get("content") if isinstance(raw.get("content"), str) else "")
            or ""
        )
        return {
            "role": "assistant",
            "content": {"type": "text", "text": text},
            "model": raw.get("model", "unknown"),
            "stopReason": raw.get("stop_reason", "endTurn"),
        }

    def invoke_world(self, args: dict) -> dict:
        res = self.request("invoke", {"tool": "world", "arguments": args})
        assert res.get("success"), res
        return res["data"]

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.request("shutdown")
        self.proc.wait(timeout=10)


def _content_text(c) -> str:
    return c if isinstance(c, str) else c.get("text", "")


def _load_pat() -> str:
    path = os.path.expanduser("~/.config/anna/credentials.json")
    with open(path, encoding="utf-8") as f:
        creds = json.load(f)
    return creds["accounts"][creds["current"]]["pat"]


def main() -> None:
    host = Host()
    try:
        init = host.request("initialize", {"protocolVersion": "2.0"})
        print(
            f"[1] initialize → v{init['protocolVersion']} capabilities={init['client_capabilities']}"
        )
        desc = host.request("describe")
        world = desc["tools"][0]
        print(
            f"[2] describe → {world['name']} timeout={world.get('timeout')} params="
            f"{[p['name'] for p in world['parameters']]}"
        )

        out = host.invoke_world({"action": "init", "spec": SPEC})
        print(f"[3] init → {out}")

        for i in (1, 2):
            t0 = time.time()
            out = host.invoke_world({"action": "tick", "n": 1})
            dt = time.time() - t0
            tick = out["results"][-1]
            story = next((r.get("day_story") for r in out["results"] if "day_story" in r), None)
            evs = [
                f"{e.get('agent_id')}/{e.get('action')}: {e.get('reason', '')[:40]}"
                for e in tick.get("events", [])
            ]
            print(f"[4.{i}] tick → tick={tick['tick']} time={tick['world_time']} dur={dt:.1f}s")
            for e in evs:
                print(f"      · {e}")
            if story:
                print(f"      📖 day story: {story['story'][:120]}…")
                print(f"      ⏳ cliffhanger: {story['cliffhanger'][:80]}")

        agent = host.invoke_world({"action": "get_agent", "agent_id": "alice"})
        print(
            f"[5] get_agent alice → goal={agent['agent']['goal'][:30]}… "
            f"rels={len(agent['relationships'])} events={len(agent['recent_events'])}"
        )

        stories = host.invoke_world({"action": "get_story"})
        print(
            f"[6] get_story → {len(stories['stories'])} 篇,day1 cliffhanger="
            f"{stories['stories'][0]['cliffhanger'][:50] if stories['stories'] else '-'}"
        )

        snap = host.kv.get("truman:run:world")
        size = len(json.dumps(snap, ensure_ascii=False).encode())
        print(f"[7] snapshot size = {size}B (KV limit 64KB)")
        mode = "mock LLM" if MOCK else "真 LLM(staging)"
        print(f"\nE2E 完成:真插件 + {mode} 全链路通过 ✅")
    finally:
        host.close()
        err = host.proc.stderr.read()
        err_lines = [ln for ln in err.splitlines() if "ready" not in ln][:6]
        if err_lines:
            print("\n--- 插件 stderr 摘要(日志地基) ---")
            for ln in err_lines:
                print(" ", ln)


if __name__ == "__main__":
    main()
