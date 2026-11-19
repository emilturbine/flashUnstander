"""Select a contiguous suffix of complete turns within a token budget."""
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence


@dataclass(frozen=True)
class Context:
    messages: list[dict[str, str]]
    turns: int
    estimated_tokens: int


def select_context(history: Sequence[Mapping], system: str, question: str,
                   count_tokens: Callable[[str], int], budget: int = 16000,
                   max_turns: int = 10) -> Context:
    if budget < 1 or max_turns < 0:
        raise ValueError("invalid context limits")
    total = count_tokens(system) + count_tokens(question)
    if total > budget:
        raise ValueError("system instruction and question exceed input budget")
    turns = []
    pending = None
    for message in history:
        if message.get("status", "complete") != "complete":
            pending = None
        elif message["role"] == "user":
            pending = message
        elif message["role"] == "assistant" and pending is not None:
            turns.append((pending, message))
            pending = None
    selected = []
    for user, assistant in reversed(turns[-max_turns:] if max_turns else []):
        cost = count_tokens(user["content"]) + count_tokens(assistant["content"])
        if total + cost > budget:
            break
        total += cost
        selected.append((user, assistant))
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    for user, assistant in reversed(selected):
        for item in (user, assistant):
            message = {"role": item["role"], "content": item["content"]}
            if item.get("image_url"):
                message["image_url"] = item["image_url"]
            messages.append(message)
    messages.append({"role": "user", "content": question})
    return Context(messages, len(selected), total)
