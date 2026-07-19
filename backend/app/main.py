import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import get_settings
from .database import (
    audit,
    create_user,
    get_db,
    get_user_by_username,
    init_db,
    list_departments,
    list_users,
    migrate_json_runtime_data,
    normalize_role,
    touch_last_login,
    update_user,
)
from .document_loader import SUPPORTED_EXTENSIONS
from .llm import stream_chat_completion
from .object_storage import object_storage
from .queue import enqueue_ingestion, health as queue_health
from .rag import (
    NO_ANSWER,
    answer_question,
    append_history,
    archive_document,
    build_messages,
    create_document_record,
    create_feedback,
    create_ingestion_job,
    create_knowledge_base,
    delete_document,
    filter_cited_sources,
    get_document,
    get_ingestion_job,
    list_audit_logs,
    list_documents,
    list_history,
    list_ingestion_jobs,
    list_knowledge_bases,
    process_ingestion_job,
    rebuild_index,
    retrieve_sources,
)
from .schemas import (
    AuditLogInfo,
    ChatRequest,
    ChatResponse,
    DeleteResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    IngestionJobInfo,
    KnowledgeBaseCreate,
    KnowledgeBaseInfo,
    LoginRequest,
    RebuildResponse,
    TokenResponse,
    UploadResponse,
    UserCreate,
    UserInfo,
    UserUpdate,
)
from .security import create_access_token, get_token_payload, require_admin, require_system_admin, verify_password
from .vector_store import vector_store


settings = get_settings()
init_db()
migrate_json_runtime_data()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    migrate_json_runtime_data()
    object_storage.ensure_bucket()
    yield


app = FastAPI(title="Enterprise RAG Bailian Demo", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    database = "ok"
    queue = "ok"
    object_store = "ok"
    try:
        with get_db() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception:
        database = "error"
    if settings.ingestion_mode == "inline":
        queue = "inline"
    else:
        try:
            queue = queue_health()
        except Exception:
            queue = "error"
    try:
        object_store = object_storage.health()
    except Exception:
        object_store = "error"
    return HealthResponse(
        status="ok" if database == "ok" and queue != "error" and object_store != "error" else "degraded",
        indexed_chunks=vector_store.count,
        documents=len(list_documents()),
        database=database,
        vector_store="pgvector" if settings.database_url.startswith("postgresql") else "sqlite_test_fallback",
        model_api="configured" if settings.dashscope_api_key else "not_configured",
        queue=queue,
        object_storage=object_store,
    )


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    user = get_user_by_username(payload.username)
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if user["status"] != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已停用")

    role = normalize_role(user["role"])
    user_info = _user_info(dict(user), role)
    token = create_access_token(
        {
            "sub": str(user["id"]),
            "username": user["username"],
            "role": role,
            "department_id": user["department_id"],
        }
    )
    touch_last_login(int(user["id"]))
    audit(int(user["id"]), "auth.login", "user", user["id"])
    return TokenResponse(access_token=token, user=user_info)


@app.get("/api/auth/me", response_model=UserInfo)
def me(payload: dict = Depends(get_token_payload)) -> UserInfo:
    user = get_user_by_username(payload["username"])
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return _user_info(dict(user), normalize_role(payload["role"]))


@app.get("/api/departments")
def departments(_: dict = Depends(require_system_admin)):
    return list_departments()


@app.get("/api/users", response_model=list[UserInfo])
def users(_: dict = Depends(require_system_admin)):
    return [_user_info(row, normalize_role(row["role"])) for row in list_users()]


@app.post("/api/users", response_model=UserInfo)
def add_user(payload: UserCreate, token: dict = Depends(require_system_admin)):
    try:
        user = create_user(
            payload.username,
            payload.password,
            payload.role,
            payload.department_id,
            payload.position,
            int(token["sub"]),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _user_info(user, normalize_role(user["role"]))


@app.patch("/api/users/{user_id}", response_model=UserInfo)
def patch_user(user_id: int, payload: UserUpdate, token: dict = Depends(require_system_admin)):
    try:
        user = update_user(user_id, payload.model_dump(exclude_unset=True), int(token["sub"]))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return _user_info(user, normalize_role(user["role"]))


@app.get("/api/knowledge-bases", response_model=list[KnowledgeBaseInfo])
def knowledge_bases(_: dict = Depends(get_token_payload)):
    return list_knowledge_bases()


@app.post("/api/knowledge-bases", response_model=KnowledgeBaseInfo)
def create_kb(payload: KnowledgeBaseCreate, token: dict = Depends(require_admin)):
    try:
        return create_knowledge_base(payload.name, payload.description, int(token["sub"]))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/documents/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    knowledge_base_id: int = 1,
    payload: dict = Depends(require_admin),
) -> UploadResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持 PDF、DOCX、TXT、MD 文件")
    if file.size and file.size > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件不能超过 {settings.max_upload_mb}MB")

    safe_name = Path(file.filename or "uploaded").name
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件不能超过 {settings.max_upload_mb}MB")
    object_key, file_hash = object_storage.put_bytes(safe_name, data, file.content_type)
    document_id, job_id = create_document_record(safe_name, object_key, file_hash, len(data), payload, knowledge_base_id)
    if settings.ingestion_mode == "inline":
        background_tasks.add_task(process_ingestion_job, job_id)
    else:
        enqueue_ingestion(job_id)
    document = get_document(document_id) or {}
    return UploadResponse(
        document_id=document_id,
        job_id=job_id,
        file_name=safe_name,
        chunks=int(document.get("chunks", 0)),
        status=document.get("status", "pending"),
        message="文件已上传，入库任务已创建",
    )


@app.post("/api/upload", response_model=UploadResponse)
async def upload_legacy(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    payload: dict = Depends(require_admin),
) -> UploadResponse:
    return await upload_document(background_tasks, file, 1, payload)


@app.post("/api/rebuild", response_model=RebuildResponse)
async def rebuild(payload: dict = Depends(require_admin)) -> RebuildResponse:
    try:
        documents, chunks = await rebuild_index(int(payload["sub"]))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return RebuildResponse(documents=documents, chunks=chunks, message="索引已重建")


@app.post("/api/documents/{document_id}/reindex", response_model=UploadResponse)
@app.post("/api/documents/{document_id}/retry", response_model=UploadResponse)
async def retry_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    payload: dict = Depends(require_admin),
) -> UploadResponse:
    document = get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    job_id = create_ingestion_job(document_id)
    if settings.ingestion_mode == "inline":
        background_tasks.add_task(process_ingestion_job, job_id)
    else:
        enqueue_ingestion(job_id)
    audit(int(payload["sub"]), "document.reindex", "document", document_id, {"job_id": job_id})
    return UploadResponse(
        document_id=document_id,
        job_id=job_id,
        file_name=document["file_name"],
        chunks=int(document["chunks"]),
        status="pending",
        message="已提交重新入库任务",
    )


@app.post("/api/documents/{document_id}/archive", response_model=DeleteResponse)
async def archive(document_id: int, payload: dict = Depends(require_admin)) -> DeleteResponse:
    archived = await archive_document(document_id, int(payload["sub"]))
    if not archived:
        raise HTTPException(status_code=404, detail="文档不存在")
    return DeleteResponse(document_id=document_id, message="文档已归档")


@app.delete("/api/documents/{document_id}", response_model=DeleteResponse)
async def remove_document(document_id: int, payload: dict = Depends(require_admin)) -> DeleteResponse:
    deleted = await delete_document(document_id, int(payload["sub"]))
    if not deleted:
        raise HTTPException(status_code=404, detail="文档不存在")
    return DeleteResponse(document_id=document_id, message="文档已删除")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, token: dict = Depends(get_token_payload)) -> ChatResponse:
    try:
        answer, sources, refused, message_id = await answer_question(
            payload.question,
            token,
            payload.top_k,
            payload.knowledge_base_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ChatResponse(answer=answer, sources=sources, refused=refused, message_id=message_id)


@app.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest, token: dict = Depends(get_token_payload)) -> StreamingResponse:
    async def event_stream():
        try:
            sources = await retrieve_sources(payload.question, token, payload.top_k, payload.knowledge_base_id)
            yield _sse("sources", [source.model_dump() for source in sources])
            refused = False
            if not sources:
                answer = NO_ANSWER
                refused = True
                yield _sse("token", answer)
            else:
                messages = build_messages(payload.question, sources)
                answer_parts: list[str] = []
                async for token_text in stream_chat_completion(messages):
                    answer_parts.append(token_text)
                    yield _sse("token", token_text)
                answer = "".join(answer_parts)
                sources = filter_cited_sources(answer, sources)
                refused = NO_ANSWER in answer
            message_id = append_history(int(token["sub"]), payload.question, answer, sources, refused)
            audit(int(token["sub"]), "chat.ask", "chat_message", message_id, {"retrieval_count": len(sources), "refused": refused})
            yield _sse("done", {"answer": answer, "sources": [source.model_dump() for source in sources], "refused": refused, "message_id": message_id})
        except Exception as exc:
            yield _sse("error", str(exc))

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/documents")
def documents(payload: dict = Depends(get_token_payload)):
    return list_documents(payload)


@app.get("/api/documents/{document_id}")
def document_detail(document_id: int, _: dict = Depends(get_token_payload)):
    document = get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return document


@app.get("/api/ingestion-jobs", response_model=list[IngestionJobInfo])
def ingestion_jobs(_: dict = Depends(require_admin)):
    return list_ingestion_jobs()


@app.get("/api/ingestion-jobs/{job_id}", response_model=IngestionJobInfo)
def ingestion_job(job_id: int, _: dict = Depends(require_admin)):
    job = get_ingestion_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@app.get("/api/history")
def history(payload: dict = Depends(get_token_payload)):
    return list_history(int(payload["sub"]), payload["role"])


@app.post("/api/feedback", response_model=FeedbackResponse)
def feedback(payload: FeedbackRequest, token: dict = Depends(get_token_payload)):
    feedback_id = create_feedback(int(token["sub"]), payload.message_id, payload.rating, payload.comment)
    return FeedbackResponse(id=feedback_id, message="反馈已记录")


@app.get("/api/audit-logs", response_model=list[AuditLogInfo])
def audit_logs(_: dict = Depends(require_system_admin)):
    return list_audit_logs()


def _sse(event: str, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _user_info(user: dict, role: str) -> UserInfo:
    return UserInfo(
        id=int(user["id"]),
        username=user["username"],
        role=role,
        department_id=user.get("department_id"),
        department_name=user.get("department_name"),
        position=user.get("position") or "",
        status=user.get("status") or "active",
    )
