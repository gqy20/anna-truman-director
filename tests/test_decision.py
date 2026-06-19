from conftest import FakeSampling

from truman_director.engine import SYSTEM_PROMPT, decide


async def test_decide_parses_model_events():
    events = [{"agent_id": "alice", "action": "move", "target": "cafe", "reason": "open up"}]
    sampling = FakeSampling(events=events)
    result = await decide(sampling, {"world_time": "08:00", "agents": {}})
    assert result == events


async def test_decide_requests_structured_output():
    sampling = FakeSampling(events=[])
    await decide(sampling, {"world_time": "08:00"})
    call = sampling.calls[0]
    assert call["max_tokens"] > 0
    assert call["response_format"]["type"] == "json_schema"
    assert call["response_format"]["json_schema"]["schema"]["properties"]["events"]
    assert "director" in SYSTEM_PROMPT.lower()


def test_decision_schema_is_strict_compatible():
    """strict:true only bites when the schema is itself strict: every object
    carries ``additionalProperties: False`` and every property (incl. the nullable
    ``target``) is required — the OpenAI-compatible hard rules that flip a backend
    from 'valid JSON' to 'conforms to schema'."""
    from truman_director.engine import DECISION_SCHEMA

    items = DECISION_SCHEMA["properties"]["events"]["items"]
    assert DECISION_SCHEMA["additionalProperties"] is False
    assert items["additionalProperties"] is False
    assert "target" in items["required"]  # required but nullable (null for `rest`)
