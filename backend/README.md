# Backend

FastAPI backend for the enterprise RAG pilot demo. It keeps a local SQLite/FAISS
fallback for development, while exposing enterprise-oriented concepts such as
knowledge bases, roles, document versions, ingestion jobs, audit logs, feedback,
and permission-aware retrieval.

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

Docker Compose sets `INGESTION_MODE=worker`, so uploads are processed by the
`worker` service instead of FastAPI inline background tasks.
