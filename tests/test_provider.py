import asyncio
from types import SimpleNamespace as NS

import pytest

from flashunstander.provider import stream_response, supports_images


class FakeStream:
    def __init__(self, events):
        self.events = events
        self.closed = False

    def __aiter__(self):
        async def iterate():
            for event in self.events:
                yield event
        return iterate()

    async def close(self):
        self.closed = True


def test_deepseek_image_stream_and_usage():
    async def scenario():
        stream = FakeStream([
            NS(usage=None, choices=[NS(delta=NS(content="hi"), finish_reason=None)]),
            NS(usage=None, choices=[NS(delta=NS(content=None), finish_reason="stop")]),
            NS(usage=NS(prompt_tokens=12, completion_tokens=2), choices=[]),
        ])
        args = {}
        async def create(**kwargs):
            args.update(kwargs)
            return stream
        client = NS(chat=NS(completions=NS(create=create)))
        events = [event async for event in stream_response(client, "deepseek", "deepseek-flash",
                  [{"role": "user", "content": "describe"}], 100, ["data:image/png;base64,AA=="])]
        assert events[0].text == "hi"
        assert events[-1].input_tokens == 12
        assert args["messages"][0]["content"][1]["type"] == "image_url"
        assert stream.closed
    asyncio.run(scenario())


def test_image_model_rejection():
    assert supports_images("deepseek", "deepseek-flash")
    assert not supports_images("deepseek", "deepseek-pro")
    async def scenario():
        with pytest.raises(ValueError):
            _ = [event async for event in stream_response(None, "deepseek", "deepseek-pro",
                 [{"role": "user", "content": "describe"}], 100, ["https://example.com/a.png"])]
    asyncio.run(scenario())
