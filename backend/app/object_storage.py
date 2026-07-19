"""S3-compatible document storage with a local test fallback."""
import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile

from .config import UPLOAD_DIR, get_settings


class ObjectStorage:
    def _client(self):
        settings = get_settings()
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError("Object storage requires boto3") from exc
        return boto3.client("s3", endpoint_url=settings.object_storage_endpoint,
            aws_access_key_id=settings.object_storage_access_key,
            aws_secret_access_key=settings.object_storage_secret_key,
            config=Config(s3={"addressing_style": "path"}))

    def _remote(self) -> bool:
        return get_settings().database_url.startswith("postgresql")

    def ensure_bucket(self) -> None:
        if not self._remote():
            return
        settings = get_settings()
        client = self._client()
        try:
            client.head_bucket(Bucket=settings.object_storage_bucket)
        except Exception:
            client.create_bucket(Bucket=settings.object_storage_bucket)

    def put_bytes(self, file_name: str, data: bytes, content_type: str | None = None) -> tuple[str, str]:
        digest = hashlib.sha256(data).hexdigest()
        key = f"uploads/{digest[:16]}/{Path(file_name).name}"
        if self._remote():
            settings = get_settings(); client = self._client()
            self.ensure_bucket()
            client.put_object(Bucket=settings.object_storage_bucket, Key=key, Body=data, ContentType=content_type or "application/octet-stream")
        else:
            target = UPLOAD_DIR / key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return key, digest

    def materialize(self, key: str, suffix: str) -> Path:
        if not self._remote(): return UPLOAD_DIR / key
        settings = get_settings(); body = self._client().get_object(Bucket=settings.object_storage_bucket, Key=key)["Body"].read()
        temp = NamedTemporaryFile(delete=False, suffix=suffix)
        temp.write(body); temp.close()
        return Path(temp.name)

    def delete(self, key: str) -> None:
        if self._remote(): self._client().delete_object(Bucket=get_settings().object_storage_bucket, Key=key)
        else: (UPLOAD_DIR / key).unlink(missing_ok=True)

    def health(self) -> str:
        if not self._remote(): return "local_fallback"
        self._client().head_bucket(Bucket=get_settings().object_storage_bucket)
        return "ok"


object_storage = ObjectStorage()
