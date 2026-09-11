import json

import pytest
from executa_sdk import SamplingError

from truman_director import engine
from truman_director.engine import _extract_json, _valid_narrative, decide


@pytest.fixture(autouse=True)
def _reset_response_format_flag():
    engine._RESPONSE_FORMAT_REJECTED = False
    yield
    engine._RESPONSE_FORMAT_REJECTED = False


class Responses:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = 0

    async def create_message(self, **kwargs):
        self.calls += 1
        return {"content": {"text": json.dumps(next(self.responses))}}


class SchemaRejectingSampling:
    """Raises -32010 whenever a response_format is attached; answers in text
    otherwise. Records every call's kwargs for assertions."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def create_message(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("response_format") is not None:
            raise SamplingError(
                -32010, "model 'MiniMax-M3' does not support json_schema response format"
            )
        return {"content": {"type": "text", "text": json.dumps(self.payload)}}


@pytest.mark.parametrize("bad", [{}, {"events": [{}]}, {"events": "bad"}, 7])
async def test_bad_decision_retries_then_fails(bad):
    sampling = Responses(bad, bad)
    with pytest.raises(ValueError, match="after retry"):
        await decide(sampling, {})
    assert sampling.calls == 2


async def test_correction_is_model_output_not_default_action():
    event = {"agent_id": "alice", "action": "rest", "target": None, "reason": "tired"}
    sampling = Responses({"events": [{}]}, {"events": [event]})
    assert await decide(sampling, {}) == [event]
    assert sampling.calls == 2


def test_unclosed_reasoning_is_not_visible_json():
    assert _extract_json('<think>example {"events": []}')[0] is None
    assert _extract_json('<think>plan</think>{"events": []}')[0] == {"events": []}


@pytest.mark.parametrize(
    "bad", [{"story": "text"}, {"story": [], "cliffhanger": "x"}, {"story": "x", "cliffhanger": ""}]
)
def test_narrative_requires_both_nonempty_strings(bad):
    assert not _valid_narrative(bad)


async def test_unsupported_response_format_degrades_to_text_mode():
    event = {"agent_id": "alice", "action": "rest", "target": None, "reason": "失眠"}
    sampling = SchemaRejectingSampling({"events": [event]})
    assert await decide(sampling, {}) == [event]
    # call 1: schema attached → -32010; call 2: same corrective attempt, text mode.
    assert [c.get("response_format") is not None for c in sampling.calls] == [True, False]
    assert all(c.get("on_unsupported") == "json_object" for c in sampling.calls)


async def test_response_format_degradation_persists_across_calls():
    sampling = SchemaRejectingSampling({"events": []})
    await decide(sampling, {})
    sampling2 = SchemaRejectingSampling({"events": []})
    await decide(sampling2, {})
    # Second process-level call never attaches the schema again.
    assert [c.get("response_format") for c in sampling2.calls] == [None]


async def test_non_capability_sampling_error_propagates():
    class Broken:
        async def create_message(self, **kwargs):
            raise SamplingError(-32005, "timeout")

    with pytest.raises(SamplingError):
        await decide(Broken(), {})
