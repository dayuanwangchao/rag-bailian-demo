import asyncio

from openai import AsyncOpenAI

from .config import get_settings
from .llm import get_async_client


async def embed_texts(texts: list[str], batch_size: int = 8) -> list[list[float]]:
    if not texts:
        return []

    settings = get_settings()
    client: AsyncOpenAI = get_async_client()
    embeddings: list[list[float]] = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = await client.embeddings.create(
            model=settings.dashscope_embedding_model,
            input=batch,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        embeddings.extend([item.embedding for item in ordered])
        if start + batch_size < len(texts):
            await asyncio.sleep(0.05)

    return embeddings
