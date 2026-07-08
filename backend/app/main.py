import json
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import UPLOAD_DIR, get_settings
from .database import get_user_by_username, init_db, migrate_json_runtime_data, row_to_dict
from .document_loader import SUPPORTED_EXTENSIONS
from .llm import stream_chat_completion
from .rag import (
    answer_question,
    append_history,
    build_messages,
    create_document_record,
    delete_document,
    filter_cited_sources,
    get_document,
    index_document,
    list_documents,
    list_history,
    rebuild_index,
    retrieve_sources,
)
from .schemas import (
    ChatRequest,
    ChatResponse,
    DeleteResponse,
    HealthResponse,
    LoginRequest,
    RebuildResponse,
    TokenResponse,
    UploadResponse,
    UserInfo,
)
from .security import create_access_token, get_token_payload, require_admin, verify_password
from .vector_store import vector_store


settings = get_settings()

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    migrate_json_runtime_data()
    yield


app = FastAPI(title="Enterprise RAG Bailian Demo", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
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


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    user = get_user_by_username(payload.username)
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    user_info = UserInfo(id=int(user["id"]), username=user["username"], role=user["role"])
    token = create_access_token({"sub": str(user["id"]), "username": user["username"], "role": user["role"]})
    return TokenResponse(access_token=token, user=user_info)


@app.get("/api/auth/me", response_model=UserInfo)
def me(payload: dict = Depends(get_token_payload)) -> UserInfo:
    return UserInfo(id=int(payload["sub"]), username=payload["username"], role=payload["role"])


@app.post("/api/upload", response_model=UploadResponse)
async def upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    payload: dict = Depends(require_admin),
) -> UploadResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持 PDF、DOCX、TXT、MD 文件")

    safe_name = Path(file.filename or "uploaded").name
    target = UPLOAD_DIR / safe_name
    with target.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    document_id = create_document_record(target, int(payload["sub"]))
    background_tasks.add_task(index_document, document_id)
    document = get_document(document_id) or {}
    return UploadResponse(
        document_id=document_id,
        file_name=safe_name,
        chunks=int(document.get("chunks", 0)),
        status=document.get("status", "pending"),
        message="文件已上传，正在后台入库",
    )


@app.post("/api/rebuild", response_model=RebuildResponse)
async def rebuild(_: dict = Depends(require_admin)) -> RebuildResponse:
    try:
        documents, chunks = await rebuild_index()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return RebuildResponse(documents=documents, chunks=chunks, message="索引已重建")


@app.post("/api/documents/{document_id}/retry", response_model=UploadResponse)
async def retry_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    _: dict = Depends(require_admin),
) -> UploadResponse:
    document = get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    background_tasks.add_task(index_document, document_id)
    return UploadResponse(
        document_id=document_id,
        file_name=document["file_name"],
        chunks=int(document["chunks"]),
        status="pending",
        message="已提交重新入库任务",
    )


@app.delete("/api/documents/{document_id}", response_model=DeleteResponse)
async def remove_document(document_id: int, _: dict = Depends(require_admin)) -> DeleteResponse:
    deleted = await delete_document(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="文档不存在")
    return DeleteResponse(document_id=document_id, message="文档已删除")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, token: dict = Depends(get_token_payload)) -> ChatResponse:
    try:
        answer, sources = await answer_question(payload.question, int(token["sub"]), payload.top_k)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ChatResponse(answer=answer, sources=sources)


@app.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest, token: dict = Depends(get_token_payload)) -> StreamingResponse:
    async def event_stream():
        try:
            sources = await retrieve_sources(payload.question, payload.top_k)
            yield _sse("sources", [source.model_dump() for source in sources])
            if not sources:
                answer = "根据当前知识库资料，无法确定答案。"
                yield _sse("token", answer)
            else:
                messages = build_messages(payload.question, sources)
                answer_parts: list[str] = []
                async for token_text in stream_chat_completion(messages):
                    answer_parts.append(token_text)
                    yield _sse("token", token_text)
                answer = "".join(answer_parts)
                sources = filter_cited_sources(answer, sources)
            append_history(int(token["sub"]), payload.question, answer, sources)
            yield _sse("done", {"answer": answer, "sources": [source.model_dump() for source in sources]})
        except Exception as exc:
            yield _sse("error", str(exc))

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/documents")
def documents(_: dict = Depends(get_token_payload)):
    return list_documents()


@app.get("/api/history")
def history(payload: dict = Depends(get_token_payload)):
    return list_history(int(payload["sub"]), payload["role"])


def _sse(event: str, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
