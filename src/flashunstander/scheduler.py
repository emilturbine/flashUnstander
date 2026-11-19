"""Bounded FIFO scheduling for independent conversation requests."""

import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass
class _Request:
    conversation_id: str
    factory: Callable[[], Awaitable[Any]]
    result: asyncio.Future
    task: asyncio.Task | None = None


class RequestScheduler:
    """Owned by one asyncio event loop; each conversation has at most one request."""

    def __init__(self, concurrency: int = 3):
        if concurrency < 1:
            raise ValueError("concurrency must be positive")
        self.concurrency = concurrency
        self._queue = deque()
        self._requests = {}
        self._running = 0
        self._closed = False

    def submit(self, conversation_id: str, factory: Callable[[], Awaitable[Any]]) -> asyncio.Future:
        if self._closed:
            raise RuntimeError("scheduler is closed")
        if conversation_id in self._requests:
            raise ValueError("conversation already has a pending request")
        result = asyncio.get_running_loop().create_future()
        request = _Request(conversation_id, factory, result)
        self._requests[conversation_id] = request
        self._queue.append(request)
        result.add_done_callback(lambda future: self._cancel_result(request) if future.cancelled() else None)
        self._dispatch()
        return result

    def cancel(self, conversation_id: str) -> bool:
        request = self._requests.get(conversation_id)
        if request is None:
            return False
        request.result.cancel()
        self._cancel_result(request)
        return True

    def _cancel_result(self, request: _Request) -> None:
        if request.task is not None:
            request.task.cancel()
        elif self._requests.get(request.conversation_id) is request:
            self._requests.pop(request.conversation_id)
            self._queue.remove(request)
            self._dispatch()

    def _dispatch(self) -> None:
        while not self._closed and self._queue and self._running < self.concurrency:
            request = self._queue.popleft()
            self._running += 1
            request.task = asyncio.create_task(self._run(request))
            request.task.add_done_callback(lambda task, item=request: self._finished(item))

    async def _run(self, request: _Request) -> None:
        try:
            value = await request.factory()
            if not request.result.done():
                request.result.set_result(value)
        except asyncio.CancelledError:
            request.result.cancel()
        except Exception as exc:
            if not request.result.done():
                request.result.set_exception(exc)

    def _finished(self, request: _Request) -> None:
        self._running -= 1
        if self._requests.get(request.conversation_id) is request:
            self._requests.pop(request.conversation_id)
        self._dispatch()

    async def close(self) -> None:
        self._closed = True
        requests = list(self._requests.values())
        for request in requests:
            self.cancel(request.conversation_id)
        tasks = [request.task for request in requests if request.task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
