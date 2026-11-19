import asyncio

import pytest

from flashunstander.mock_stream import mock_stream


def test_stream_preserves_chunks_and_usage():
    async def collect():
        return [event async for event in mock_stream(["你", "好"], input_tokens=4, output_tokens=2)]

    events = asyncio.run(collect())
    assert [event.text for event in events[:-1]] == ["你", "好"]
    assert events[-1].kind == "completed"
    assert (events[-1].input_tokens, events[-1].output_tokens) == (4, 2)


def test_stream_failure_retains_prior_chunks():
    async def collect():
        seen = []
        with pytest.raises(ConnectionError):
            async for event in mock_stream(["a", "b"], fail_after=1):
                seen.append(event.text)
        return seen

    assert asyncio.run(collect()) == ["a"]


def test_waiting_stream_can_be_cancelled():
    async def cancel():
        gate = asyncio.Event()

        async def consume():
            return [event async for event in mock_stream(["a"], gate=gate)]

        task = asyncio.create_task(consume())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel())
