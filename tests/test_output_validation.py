import json

import pytest

from truman_director.engine import _extract_json, _valid_narrative, decide


class Responses:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = 0

    async def create_message(self, **kwargs):
        self.calls += 1
        return {"content": {"text": json.dumps(next(self.responses))}}


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
