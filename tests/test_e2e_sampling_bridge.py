"""Do not lose system instructions in the real-model diagnostic driver."""

import runpy
from pathlib import Path


def test_system_prompt_is_a_message(monkeypatch):
    namespace = runpy.run_path(str(Path(__file__).parents[1] / "scripts/local_e2e.py"))
    host_type = namespace["Host"]
    host = object.__new__(host_type)  # No child process/network needed.
    captured = {}

    def request(url, body, headers, timeout):
        captured.update(body)
        return {"content": "ok", "stopReason": "endTurn", "usage": {"outputTokens": 1}}

    monkeypatch.setitem(host_type._sampling.__globals__, "MOCK", False)
    monkeypatch.setitem(host_type._sampling.__globals__, "_http_post_json", request)
    monkeypatch.setattr(host_type, "_mint", lambda self: "test-only")
    result = host._sampling(
        {
            "systemPrompt": "Return JSON only",
            "maxTokens": 4096,
            "messages": [{"role": "user", "content": {"text": "world"}}],
        }
    )
    assert "system" not in captured
    assert captured["messages"] == [
        {"role": "system", "content": "Return JSON only"},
        {"role": "user", "content": "world"},
    ]
    assert result["usage"] == {"outputTokens": 1}
    assert result["stopReason"] == "endTurn"
