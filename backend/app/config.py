from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
INDEX_DIR = DATA_DIR / "indexes"


class Settings(BaseSettings):
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_chat_model: str = "qwen-plus"
    dashscope_embedding_model: str = "text-embedding-v4"
    top_k: int = 5
    chunk_size: int = 800
    chunk_overlap: int = 120
    similarity_threshold: float = 0.2
    max_upload_mb: int = 100
    # Docker Compose sets the production PostgreSQL URL. SQLite is test-only.
    database_url: str = "sqlite:///data/rag.db"
    redis_url: str = "redis://redis:6379/0"
    object_storage_endpoint: str = "http://minio:9000"
    object_storage_access_key: str = "ragminio"
    object_storage_secret_key: str = "ragminio123"
    object_storage_bucket: str = "rag-documents"
    ingestion_queue: str = "rag:ingestion"
    ingestion_mode: str = "queue"
    jwt_secret_key: str = "change-this-secret-in-production"
    access_token_minutes: int = 720
    cors_origins: str = "http://localhost:5176,http://127.0.0.1:5176,http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()
