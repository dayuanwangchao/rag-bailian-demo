"""Redis-backed ingestion queue.  The worker owns task execution."""
import asyncio

from .config import get_settings


def _redis():
    try:
        import redis
    except ImportError as exc:
        raise RuntimeError("Redis queue requires redis") from exc
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


def enqueue_ingestion(job_id: int) -> None:
    _redis().rpush(get_settings().ingestion_queue, str(job_id))


async def dequeue_ingestion(timeout: int = 5) -> int | None:
    result = await asyncio.to_thread(_redis().blpop, get_settings().ingestion_queue, timeout)
    return int(result[1]) if result else None


def health() -> str:
    _redis().ping()
    return "ok"
