"""Coordinate persisted conversations and independent streamed requests.

Create and use the service on the same thread and asyncio event loop as Store.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from .context import select_context
from .scheduler import RequestScheduler


@dataclass(frozen=True)
class ServiceEvent:
    run_id: str
    conversation_id: str
    kind: str
    text: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None


class ConversationService:
    def __init__(self, store, scheduler: RequestScheduler):
        self.store = store
        self.scheduler = scheduler
        self._active = {}

    def submit(self, conversation_id, question, stream_factory, count_tokens: Callable,
               *, system="", budget=16000, max_turns=10, on_event=None, image_url=None,
               model=None, parameters=None):
        if conversation_id in self._active:
            raise ValueError("conversation already has a pending request")
        if not question.strip() and not image_url:
            raise ValueError("question must not be empty")
        history = self.store.messages(conversation_id, limit=max(50, max_turns * 2))
        context = select_context(history, system, question, count_tokens, budget, max_turns)
        if image_url:
            context.messages[-1]["image_url"] = image_url
        run_id = uuid4().hex
        self.store.add_message(conversation_id, "user", question, image_url=image_url)
        answer_id = self.store.add_message(conversation_id, "assistant", "", "queued")
        self.store.create_run(run_id, conversation_id, answer_id, model, parameters)
        self._active[conversation_id] = run_id
        started = False
        submitted_at = time.monotonic()
        queue_seconds = None
        first_text_seconds = None

        def record(status, input_tokens=None, output_tokens=None):
            self.store.update_run(run_id, status=status, queue_seconds=queue_seconds,
                                  first_text_seconds=first_text_seconds,
                                  total_seconds=time.monotonic() - submitted_at,
                                  input_tokens=input_tokens, output_tokens=output_tokens)

        def finish(status, text, input_tokens=None, output_tokens=None):
            self.store.finish_run(run_id, answer_id, text, status, queue_seconds=queue_seconds,
                                  first_text_seconds=first_text_seconds,
                                  total_seconds=time.monotonic() - submitted_at,
                                  input_tokens=input_tokens, output_tokens=output_tokens)

        def emit(kind, text="", input_tokens=None, output_tokens=None):
            if on_event:
                on_event(ServiceEvent(run_id, conversation_id, kind, text, input_tokens, output_tokens))

        async def run():
            nonlocal started, queue_seconds, first_text_seconds
            started = True
            queue_seconds = time.monotonic() - submitted_at
            record("streaming")
            text = ""
            last_saved = time.monotonic()
            self.store.update_message(answer_id, text, "streaming")
            emit("started")
            try:
                async for event in stream_factory(context.messages):
                    if event.kind == "text":
                        if first_text_seconds is None:
                            first_text_seconds = time.monotonic() - submitted_at
                        text += event.text
                        if time.monotonic() - last_saved >= 1:
                            self.store.update_message(answer_id, text, "streaming")
                            last_saved = time.monotonic()
                        emit("text", event.text)
                    elif event.kind in {"reasoning", "search"}:
                        # Process details are for this window only, not assistant context.
                        emit(event.kind, event.text)
                    elif event.kind in {"completed", "truncated"}:
                        status = "complete" if event.kind == "completed" else "truncated"
                        finish(status, text, event.input_tokens, event.output_tokens)
                        emit(event.kind, input_tokens=event.input_tokens, output_tokens=event.output_tokens)
                        return
                raise RuntimeError("stream ended without completion")
            except asyncio.CancelledError:
                finish("cancelled", text)
                emit("cancelled")
                raise
            except Exception:
                finish("failed", text)
                emit("failed")
                raise

        try:
            future = self.scheduler.submit(conversation_id, run)
        except Exception:
            self._active.pop(conversation_id, None)
            finish("failed", "")
            raise

        def finished(done):
            if done.cancelled() and not started:
                finish("cancelled", "")
                emit("cancelled")
            if self._active.get(conversation_id) == run_id:
                self._active.pop(conversation_id, None)

        future.add_done_callback(finished)
        return run_id, future, context

    def cancel(self, conversation_id):
        return self.scheduler.cancel(conversation_id)
