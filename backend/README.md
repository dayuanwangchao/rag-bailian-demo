# Backend

FastAPI backend for the enterprise RAG demo.

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
admin / admin123
user  / user123
```

## Test

```powershell
python -m pytest
```
