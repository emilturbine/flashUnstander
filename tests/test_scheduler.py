import asyncio

import pytest

from flashunstander.scheduler import RequestScheduler


def test_fifo_cancellation_and_conversation_exclusion():
    async def scenario():
        scheduler = RequestScheduler(3)
        gate = asyncio.Event()
        started = []

        async def work(name):
            started.append(name)
            await gate.wait()
            return name

        futures = [scheduler.submit(str(i), lambda i=i: work(i)) for i in range(4)]
        with pytest.raises(ValueError):
            scheduler.submit("0", lambda: work(9))
        await asyncio.sleep(0)
        assert started == [0, 1, 2]
        assert scheduler.cancel("0")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert started == [0, 1, 2, 3]
        gate.set()
        assert await futures[3] == 3
        await scheduler.close()

    asyncio.run(scenario())


def test_cancel_queued_never_invokes_factory_and_close_cleans_up():
    async def scenario():
        scheduler = RequestScheduler(1)
        called = []

        async def blocked():
            await asyncio.Event().wait()

        scheduler.submit("first", blocked)
        queued = scheduler.submit("second", lambda: called.append(True))
        assert scheduler.cancel("second")
        assert queued.cancelled()
        await scheduler.close()
        assert not called
        with pytest.raises(RuntimeError):
            scheduler.submit("third", blocked)

    asyncio.run(scenario())
