import asyncio
import logging

from .database import init_db
from .queue import dequeue_ingestion
from .rag import process_ingestion_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def run_worker() -> None:
    init_db()
    logging.info("Redis ingestion worker started")
    while True:
        job_id = await dequeue_ingestion()
        if job_id is None:
            continue
        logging.info("processing ingestion job %s", job_id)
        await process_ingestion_job(job_id)


if __name__ == "__main__":
    asyncio.run(run_worker())
