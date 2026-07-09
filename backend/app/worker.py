import asyncio
import logging

from .database import get_db, init_db
from .rag import process_ingestion_job


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def run_worker() -> None:
    init_db()
    logging.info("ingestion worker started")
    while True:
        job_id = _next_pending_job()
        if job_id is None:
            await asyncio.sleep(2)
            continue
        logging.info("processing ingestion job %s", job_id)
        await process_ingestion_job(job_id)


def _next_pending_job() -> int | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM ingestion_jobs
            WHERE status = 'pending'
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            """
            UPDATE ingestion_jobs
            SET status = 'parsing', started_at = COALESCE(started_at, CURRENT_TIMESTAMP), retry_count = retry_count + 1
            WHERE id = ?
            """,
            (int(row["id"]),),
        )
        return int(row["id"])


if __name__ == "__main__":
    asyncio.run(run_worker())
