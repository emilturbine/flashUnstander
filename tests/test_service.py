import asyncio

from flashunstander.mock_stream import mock_stream
from flashunstander.provider import StreamEvent
from flashunstander.scheduler import RequestScheduler
from flashunstander.service import ConversationService
from flashunstander.storage import Store


def test_service_persists_stream_and_reuses_context(tmp_path):
    async def scenario():
        store = Store(tmp_path / "history.db")
        conversation = store.create_conversation()
        scheduler = RequestScheduler()
        service = ConversationService(store, scheduler)
        received = []

        def stream(messages):
            received.append(messages)
            return mock_stream(["hello", " world"], input_tokens=2, output_tokens=3)

        run_id, first, _ = service.submit(conversation, "first", stream, len,
                                           model="example", parameters={"max_output_tokens": 50})
        await first
        run = store.run(run_id)
        assert run["status"] == "complete"
        assert run["model"] == "example"
        assert run["input_tokens"] == 2 and run["output_tokens"] == 3
        assert run["queue_seconds"] is not None and run["first_text_seconds"] is not None
        await asyncio.sleep(0)
        _, second, context = service.submit(conversation, "second", stream, len)
        await second
        assert context.turns == 1
        assert [m["content"] for m in received[1]] == ["first", "hello world", "second"]
        assert store.messages(conversation)[-1]["status"] == "complete"
        await scheduler.close()
        store.close()

    asyncio.run(scenario())


def test_process_events_stay_out_of_persisted_answer(tmp_path):
    async def scenario():
        store = Store(tmp_path / "history.db")
        conversation = store.create_conversation()
        scheduler = RequestScheduler()
        service = ConversationService(store, scheduler)
        observed = []

        async def generate(_messages):
            yield StreamEvent("reasoning", "process details")
            yield StreamEvent("search", "search details")
            yield StreamEvent("text", "partial answer")
            yield StreamEvent("truncated", input_tokens=10, output_tokens=20)

        try:
            run_id, future, _ = service.submit(conversation, "question", generate, len, on_event=observed.append)
            await future
            assert [event.kind for event in observed] == ["started", "reasoning", "search", "text", "truncated"]
            assert store.messages(conversation)[-1]["content"] == "partial answer"
            assert store.run(run_id)["status"] == "truncated"
            assert store.run(run_id)["output_tokens"] == 20
        finally:
            await scheduler.close()
            store.close()

    asyncio.run(scenario())
