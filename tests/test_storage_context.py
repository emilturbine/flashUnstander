import pytest

from flashunstander.context import select_context
from flashunstander.storage import Store


def test_context_can_select_rounds_near_100k_budget():
    history = [
        {"role": role, "content": "x" * 24_000, "status": "complete"}
        for _ in range(3) for role in ("user", "assistant")
    ]
    context = select_context(history, "", "question", len, budget=100_000, max_turns=5)
    assert context.turns == 2
    assert context.estimated_tokens == 96_008
    no_history = select_context(history, "", "question", len, budget=100_000, max_turns=0)
    assert no_history.turns == 0


def test_run_finish_is_atomic_and_recovery_preserves_partial_answer(tmp_path):
    store = Store(tmp_path / "runs.db")
    conversation = store.create_conversation()
    answer = store.add_message(conversation, "assistant", "partial", "streaming")
    store.create_run("run", conversation, answer)
    with pytest.raises(KeyError):
        store.finish_run("missing", answer, "new", "complete")
    assert store.messages(conversation)[0]["content"] == "partial"
    store.recover_interrupted()
    assert store.messages(conversation)[0]["status"] == "interrupted"
    assert store.run("run")["status"] == "interrupted"
    store.close()


def test_persistence_and_pagination(tmp_path):
    path = tmp_path / "history.db"
    store = Store(path)
    conversation = store.create_conversation()
    store.add_message(conversation, "user", "first")
    store.add_message(conversation, "assistant", "answer")
    store.add_message(conversation, "user", "second")
    store.close()
    store = Store(path)
    page = store.messages(conversation, limit=2)
    assert [item["content"] for item in page] == ["answer", "second"]
    assert store.messages(conversation, before=page[0]["sequence"])[0]["content"] == "first"
    store.close()


def test_budget_keeps_complete_recent_turns():
    history = [dict(role=role, content=content, status=status) for role, content, status in [
        ("user", "old", "complete"), ("assistant", "old answer", "complete"),
        ("user", "new", "complete"), ("assistant", "ok", "complete"),
        ("user", "broken", "complete"), ("assistant", "partial", "cancelled"),
    ]]
    result = select_context(history, "", "?", len, budget=7)
    assert result.turns == 1
    assert [item["content"] for item in result.messages] == ["new", "ok", "?"]
    with pytest.raises(ValueError):
        select_context([], "system", "question", len, budget=1)


def test_image_survives_reopen_and_context(tmp_path):
    path = tmp_path / "history.db"
    store = Store(path)
    conversation = store.create_conversation()
    store.add_message(conversation, "user", "describe", image_url="data:image/png;base64,YQ==")
    store.add_message(conversation, "assistant", "image")
    store.close()
    store = Store(path)
    context = select_context(store.messages(conversation), "", "more", len)
    assert context.messages[0]["image_url"] == "data:image/png;base64,YQ=="
    store.close()
