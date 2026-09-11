import json

from truman_director import diagnostics


def test_trace_redacts_untrusted_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUMAN_TRACE_DIR", str(tmp_path))
    original_handlers = diagnostics._trace.handlers[:]
    original_level = diagnostics._trace.level
    try:
        diagnostics.configure()
        diagnostics.event("stdin_received", "secret-token", "secret-method", "secret-action")
        diagnostics.event("invoke_exit", 1, "invoke", "list_scenarios", 1.234)
        content = next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8")
        assert "secret" not in content
        rows = [json.loads(line) for line in content.splitlines()]
        assert rows[1]["method"] == rows[1]["action"] == "other"
        assert rows[2]["action"] == "list_scenarios"
        assert rows[2]["elapsed_ms"] == 1.2
    finally:
        for handler in diagnostics._trace.handlers[:]:
            if handler not in original_handlers:
                diagnostics._trace.removeHandler(handler)
                handler.close()
        diagnostics._trace.setLevel(original_level)
