"""Streaming providers with a small application-owned event interface."""
from dataclasses import dataclass
from typing import Any, AsyncIterator


@dataclass(frozen=True)
class StreamEvent:
    kind: str
    text: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None


def supports_images(provider: str, model: str) -> bool:
    """Return whether the configured provider/model supports image input.

    OpenAI model capabilities must be explicitly selected by the caller; model
    families evolve and an unknown name should not silently accept images.
    """
    if provider == "deepseek":
        return model in {"deepseek-flash", "deepseek-v4-flash-vision-exp"}
    if provider == "openai":
        return model.startswith(("gpt-4o", "gpt-4.1", "gpt-5", "gpt-6"))
    return False


def supports_thinking(provider: str, model: str) -> bool:
    return provider == "deepseek" and (
        model in {"deepseek-flash", "deepseek-chat", "deepseek-reasoner"}
        or model.startswith("deepseek-v4-")
    )


def supports_search(provider: str, model: str) -> bool:
    return provider == "deepseek" and model == "deepseek-flash"


def _format_search_event(stage: str, call: dict) -> str:
    action = call.get("action") or {}
    action_labels = {"search": "搜索", "open_page": "打开网页", "find_in_page": "查找网页内容"}
    label = action_labels.get(action.get("type"), "在线搜索")
    queries = action.get("queries") or []
    target = "、".join(queries) if queries else action.get("url")
    if stage == "call_started":
        return f"{label}：{target}\n" if target else f"{label}中…\n"
    if call.get("status") == "failed":
        return f"{label}失败\n"
    sources = call.get("sources") or ([call["page"]] if call.get("page") else [])
    titles = [source.get("title") or source.get("url") for source in sources[:5]]
    titles = [title for title in titles if title]
    return f"{label}结果：{'、'.join(titles)}\n" if titles else f"{label}完成\n"


async def stream_response(client: Any, provider: str, model: str,
                          messages: list[dict], max_output_tokens: int,
                          image_urls: list[str] | None = None, *,
                          thinking: bool = False, search: bool = False) -> AsyncIterator[StreamEvent]:
    """Stream text and final usage. The caller owns the async client and cancellation.

    Images are URL or data URLs supplied by the caller, and apply to the final
    user message. Errors propagate so partial output can be retained upstream.
    """
    images = image_urls or []
    if provider not in {"openai", "deepseek"}:
        raise ValueError("unsupported provider")
    if thinking and not supports_thinking(provider, model):
        raise ValueError("当前模型没有启用思考的接口")
    if search and not supports_search(provider, model):
        raise ValueError("在线搜索目前支持 DeepSeek 的 deepseek-flash")
    if not messages or messages[-1].get("role") != "user":
        raise ValueError("the last message must be a user message")
    if (images or any(message.get("image_url") for message in messages)) and not supports_images(provider, model):
        raise ValueError("the selected model does not support images")
    prepared = [dict(message) for message in messages]
    for message in prepared:
        image = message.pop("image_url", None)
        if image:
            if provider == "openai":
                message["content"] = [{"type": "input_text", "text": message["content"]},
                                      {"type": "input_image", "image_url": image}]
            else:
                message["content"] = [{"type": "text", "text": message["content"]},
                                      {"type": "image_url", "image_url": {"url": image}}]
    if provider == "openai":
        if images:
            prepared[-1]["content"] = ([{"type": "input_text", "text": prepared[-1]["content"]}]
                + [{"type": "input_image", "image_url": url} for url in images])
        stream = await client.responses.create(model=model, input=prepared, stream=True,
                                               store=False, max_output_tokens=max_output_tokens)
        try:
            async for event in stream:
                if event.type == "response.output_text.delta":
                    yield StreamEvent("text", text=event.delta)
                elif event.type == "response.completed" or (
                    event.type == "response.incomplete"
                    and getattr(event.response.incomplete_details, "reason", None) == "max_output_tokens"
                ):
                    usage = event.response.usage
                    kind = "completed" if event.type == "response.completed" else "truncated"
                    yield StreamEvent(kind, input_tokens=usage.input_tokens if usage else None,
                                      output_tokens=usage.output_tokens if usage else None)
                elif event.type in {"response.failed", "response.incomplete", "error"}:
                    raise RuntimeError(f"response ended with {event.type}")
        finally:
            await stream.close()
    else:
        if images:
            prepared[-1]["content"] = ([{"type": "text", "text": prepared[-1]["content"]}]
                + [{"type": "image_url", "image_url": {"url": url}} for url in images])
        options: dict[str, Any] = {}
        if supports_thinking(provider, model):
            options["thinking"] = {"type": "enabled" if thinking else "disabled"}
        if search:
            options["tools"] = [{"type": "deepseek_web_search"}]
        stream = await client.chat.completions.create(
            model=model, messages=prepared, stream=True, max_tokens=max_output_tokens,
            stream_options={"include_usage": True}, extra_body=options,
        )
        usage = None
        finish_reason = None
        saw_search_event = False
        try:
            async for chunk in stream:
                if getattr(chunk, "error", None):
                    raise RuntimeError("DeepSeek 未能完成生成")
                if getattr(chunk, "usage", None) is not None:
                    usage = chunk.usage
                for choice in chunk.choices:
                    if thinking and (reasoning := getattr(choice.delta, "reasoning_content", None)):
                        yield StreamEvent("reasoning", text=reasoning)
                    progress = getattr(choice, "server_tool_event", None) if search else None
                    if progress and (stage := progress.get("type")) in {"call_started", "call_completed"}:
                        saw_search_event = True
                        yield StreamEvent("search", text=_format_search_event(stage, progress.get("call") or {}))
                    if search and not saw_search_event:
                        for step in getattr(choice.delta, "server_tool_calls", None) or ():
                            for call in step.get("calls", ()):
                                yield StreamEvent("search", text=_format_search_event("call_started", call))
                                yield StreamEvent("search", text=_format_search_event("call_completed", call))
                    if content := getattr(choice.delta, "content", None):
                        yield StreamEvent("text", text=content)
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
            if finish_reason not in {"stop", "length"}:
                raise RuntimeError(f"response ended with {finish_reason or 'no finish reason'}")
            kind = "truncated" if finish_reason == "length" else "completed"
            yield StreamEvent(kind, input_tokens=usage.prompt_tokens if usage else None,
                              output_tokens=usage.completion_tokens if usage else None)
        finally:
            await stream.close()
