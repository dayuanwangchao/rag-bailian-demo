import json
import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import UPLOAD_DIR
from .document_loader import SUPPORTED_EXTENSIONS
from .llm import stream_chat_completion
from .rag import (
    answer_question,
    append_history,
    build_messages,
    list_documents,
    list_history,
    rebuild_index,
    retrieve_sources,
)
from .schemas import ChatRequest, ChatResponse, HealthResponse, RebuildResponse, UploadResponse
from .vector_store import vector_store


app = FastAPI(title="RAG Bailian Demo", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        indexed_chunks=vector_store.count,
        documents=len(list_documents()),
    )


@app.post("/api/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)) -> UploadResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, TXT and MD files are supported")

    safe_name = Path(file.filename or "uploaded").name
    target = UPLOAD_DIR / safe_name
    with target.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        await rebuild_index()
        document = next((item for item in list_documents() if item["file_name"] == safe_name), None)
        chunks = document["chunks"] if document else 0
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return UploadResponse(file_name=safe_name, chunks=chunks, message="File uploaded and indexed")


@app.post("/api/rebuild", response_model=RebuildResponse)
async def rebuild() -> RebuildResponse:
    try:
        documents, chunks = await rebuild_index()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return RebuildResponse(documents=documents, chunks=chunks, message="Index rebuilt")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    try:
        answer, sources = await answer_question(payload.question, payload.top_k)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ChatResponse(answer=answer, sources=sources)


@app.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    async def event_stream():
        try:
            sources = await retrieve_sources(payload.question, payload.top_k)
            yield _sse("sources", [source.model_dump() for source in sources])
            messages = build_messages(payload.question, sources)
            answer_parts: list[str] = []
            async for token in stream_chat_completion(messages):
                answer_parts.append(token)
                yield _sse("token", token)
            answer = "".join(answer_parts)
            append_history(payload.question, answer, sources)
            yield _sse("done", {"answer": answer})
        except Exception as exc:
            yield _sse("error", str(exc))

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/documents")
def documents():
    return list_documents()


@app.get("/api/history")
def history():
    return list_history()


def _sse(event: str, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
