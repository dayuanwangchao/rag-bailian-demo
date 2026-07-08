from pydantic import BaseModel, Field


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
    file_name: str
    size: int
    chunks: int = 0


class UploadResponse(BaseModel):
    file_name: str
    chunks: int
    message: str


class RebuildResponse(BaseModel):
    documents: int
    chunks: int
    message: str


class HealthResponse(BaseModel):
    status: str
    indexed_chunks: int
    documents: int
