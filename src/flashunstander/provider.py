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


async def stream_response(client: Any, provider: str, model: str,
                          messages: list[dict], max_output_tokens: int,
                          image_urls: list[str] | None = None) -> AsyncIterator[StreamEvent]:
    """Stream text and final usage. The caller owns the async client and cancellation.

    Images are URL or data URLs supplied by the caller, and apply to the final
    user message. Errors propagate so partial output can be retained upstream.
    """
    images = image_urls or []
    if provider not in {"openai", "deepseek"}:
        raise ValueError("unsupported provider")
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
                elif event.type == "response.completed":
                    usage = event.response.usage
                    yield StreamEvent("completed", input_tokens=usage.input_tokens if usage else None,
                                      output_tokens=usage.output_tokens if usage else None)
                elif event.type in {"response.failed", "response.incomplete", "error"}:
                    raise RuntimeError(f"response ended with {event.type}")
        finally:
            await stream.close()
    else:
        if images:
            prepared[-1]["content"] = ([{"type": "text", "text": prepared[-1]["content"]}]
                + [{"type": "image_url", "image_url": {"url": url}} for url in images])
        stream = await client.chat.completions.create(model=model, messages=prepared, stream=True,
            max_tokens=max_output_tokens, stream_options={"include_usage": True})
        usage = None
        finish_reason = None
        try:
            async for chunk in stream:
                if chunk.usage is not None:
                    usage = chunk.usage
                for choice in chunk.choices:
                    if choice.delta.content:
                        yield StreamEvent("text", text=choice.delta.content)
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
            if finish_reason != "stop":
                raise RuntimeError(f"response ended with {finish_reason or 'no finish reason'}")
            yield StreamEvent("completed", input_tokens=usage.prompt_tokens if usage else None,
                              output_tokens=usage.completion_tokens if usage else None)
        finally:
            await stream.close()
