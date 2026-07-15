from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from .config import get_settings


def get_async_client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is not configured")
    return AsyncOpenAI(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        timeout=60.0,
    )


async def chat_completion(messages: list[dict[str, str]]) -> str:
    settings = get_settings()
    client = get_async_client()
    response = await client.chat.completions.create(
        model=settings.dashscope_chat_model,
        messages=messages,
        temperature=0.2,
    )
    return response.choices[0].message.content or ""


async def stream_chat_completion(messages: list[dict[str, str]]) -> AsyncGenerator[str, None]:
    settings = get_settings()
    client = get_async_client()
    stream = await client.chat.completions.create(
        model=settings.dashscope_chat_model,
        messages=messages,
        temperature=0.2,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
