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
