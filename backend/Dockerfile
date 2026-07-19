FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
# Local data directories are only used by the SQLite test fallback. Production
# documents live in MinIO and vectors live in PostgreSQL/pgvector.
COPY data/uploads/.gitkeep ./data/uploads/.gitkeep

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
