# Backend

FastAPI backend for the enterprise RAG pilot demo. Docker deployments use
PostgreSQL + pgvector for shared metadata/vector retrieval, Redis for ingestion
jobs, and MinIO for original files. SQLite is retained only as a lightweight
test fallback. The API exposes knowledge bases, roles, document versions,
ingestion jobs, audit logs, feedback, and permission-aware retrieval.

## Start

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Demo Accounts

```text
system_admin: admin / admin123
kb_admin:     kbadmin / kbadmin123
editor:       editor / editor123
reader:       user  / user123
```

## Enterprise APIs

- `GET /api/knowledge-bases`
- `POST /api/knowledge-bases`
- `POST /api/documents/upload`
- `POST /api/documents/{id}/reindex`
- `POST /api/documents/{id}/archive`
- `GET /api/ingestion-jobs`
- `GET /api/audit-logs`
- `POST /api/feedback`

## Test

```powershell
python -m pytest
```

## Docker Mode

The root project provides one-click scripts:

```powershell
cd E:\CodexWorkspace\rag-bailian-demo
.\start-docker.ps1 -Build
.\stop-docker.ps1
```

Docker Compose sets `INGESTION_MODE=queue`, so uploads are persisted to MinIO
and queued in Redis; the `worker` service processes them independently of the
API service.

## Migrate the legacy demo data

With the cloud services running and `DATABASE_URL` pointing to PostgreSQL,
run the one-time importer below. It copies metadata, moves readable legacy
uploads to MinIO, and queues a clean embedding rebuild (legacy FAISS files are
not reused):

```powershell
python scripts/migrate_sqlite_to_postgres.py data/rag.db
```
