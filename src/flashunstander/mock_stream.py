"""Deterministic asynchronous stream for exercising request consumers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class MockEvent:
    kind: str
    text: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None


async def mock_stream(
    chunks: Iterable[str],
    *,
    gate: asyncio.Event | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    fail_after: int | None = None,
) -> AsyncIterator[MockEvent]:
    """Yield text and a completion event; gate permits deterministic cancellation.

    If supplied, fail_after raises after that many chunks, including zero.
    Cancellation is allowed to propagate to the caller.
    """
    if fail_after is not None and fail_after < 0:
        raise ValueError("fail_after must be non-negative")
    if gate is not None:
        await gate.wait()
    count = 0
    for index, chunk in enumerate(chunks):
        if index == fail_after:
            raise ConnectionError("simulated stream failure")
        await asyncio.sleep(0)
        yield MockEvent(kind="text", text=chunk)
        count += 1
    if fail_after is not None and fail_after == count:
        raise ConnectionError("simulated stream failure")
    yield MockEvent(kind="completed", input_tokens=input_tokens, output_tokens=output_tokens)
