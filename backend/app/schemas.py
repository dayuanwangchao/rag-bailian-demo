from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class UserInfo(BaseModel):
    id: int
    username: str
    role: str
    department_id: int | None = None
    department_name: str | None = None
    position: str = ""
    status: str = "active"


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=40)
    password: str = Field(..., min_length=6, max_length=128)
    role: str = Field(..., pattern="^(system_admin|kb_admin|editor|reader)$")
    department_id: int | None = None
    position: str = Field(default="", max_length=80)


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(system_admin|kb_admin|editor|reader)$")
    department_id: int | None = None
    position: str | None = Field(default=None, max_length=80)
    status: str | None = Field(default=None, pattern="^(active|disabled)$")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)


class KnowledgeBaseInfo(BaseModel):
    id: int
    name: str
    description: str = ""
    owner_id: int | None = None
    created_at: datetime | None = None


class Source(BaseModel):
    id: int
    file_name: str
    chunk_id: int
    content: str
    score: float | None = None
    knowledge_base_id: int | None = None
    document_id: int | None = None
    document_version: int | None = None
    section_title: str = ""
    page_start: int | None = None
    page_end: int | None = None


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=30)
    knowledge_base_id: int | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    refused: bool = False
    message_id: int | None = None


class DocumentInfo(BaseModel):
    id: int
    knowledge_base_id: int = 1
    file_name: str
    size: int
    file_type: str = ""
    status: str = "pending"
    chunks: int = 0
    current_version: int = 1
    uploaded_by: int | None = None
    uploaded_at: datetime | None = None
    department_scope: list[int] = []
    visible_roles: list[str] = []
    visible_users: list[int] = []
    classification: str = "internal"
    archived_at: datetime | None = None
    error_message: str | None = None


class UploadResponse(BaseModel):
    document_id: int
    job_id: int | None = None
    file_name: str
    chunks: int
    status: str
    message: str


class RebuildResponse(BaseModel):
    documents: int
    chunks: int
    message: str


class IngestionJobInfo(BaseModel):
    id: int
    document_id: int
    status: str
    progress: int = 0
    retry_count: int = 0
    error_message: str | None = None
    log_summary: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    file_name: str | None = None


class FeedbackRequest(BaseModel):
    message_id: int | None = None
    rating: str = Field(..., pattern="^(helpful|not_helpful|citation_error|incomplete)$")
    comment: str = Field(default="", max_length=1000)


class FeedbackResponse(BaseModel):
    id: int
    message: str


class AuditLogInfo(BaseModel):
    id: int
    actor_id: int | None = None
    username: str | None = None
    action: str
    target_type: str = ""
    target_id: str = ""
    metadata: dict = {}
    created_at: datetime | None = None


class HealthResponse(BaseModel):
    status: str
    indexed_chunks: int
    documents: int
    database: str = "ok"
    vector_store: str = "ok"
    model_api: str = "not_checked"
    queue: str = "not_checked"
    object_storage: str = "not_checked"


class DeleteResponse(BaseModel):
    document_id: int
    message: str
