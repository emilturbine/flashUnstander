import pytest

from flashunstander.context import select_context
from flashunstander.storage import Store


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
