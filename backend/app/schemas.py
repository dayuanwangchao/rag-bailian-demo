from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class UserInfo(BaseModel):
    id: int
    username: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class Source(BaseModel):
    id: int
    file_name: str
    chunk_id: int
    content: str
    score: float | None = None


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=20)


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


class DocumentInfo(BaseModel):
    id: int
    file_name: str
    size: int
    file_type: str = ""
    status: str = "pending"
    chunks: int = 0
    uploaded_by: int | None = None
    uploaded_at: str | None = None
    error_message: str | None = None


class UploadResponse(BaseModel):
    document_id: int
    file_name: str
    chunks: int
    status: str
    message: str


class RebuildResponse(BaseModel):
    documents: int
    chunks: int
    message: str


class HealthResponse(BaseModel):
    status: str
    indexed_chunks: int
    documents: int


class DeleteResponse(BaseModel):
    document_id: int
    message: str
