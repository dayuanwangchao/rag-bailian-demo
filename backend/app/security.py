import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings
security = HTTPBearer(auto_error=False)
ADMIN_ROLES = {"system_admin", "kb_admin", "editor", "admin"}


def normalize_role(role: str) -> str:
    if role == "admin":
        return "system_admin"
    if role == "user":
        return "reader"
    return role


def is_admin_role(role: str) -> bool:
    return normalize_role(role) in ADMIN_ROLES


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    salt, expected = password_hash.split("$", 1)
    digest = hash_password(password, salt).split("$", 1)[1]
    return hmac.compare_digest(digest, expected)


def create_access_token(payload: dict[str, Any]) -> str:
    settings = get_settings()
    now = int(time.time())
    body = {
        **payload,
        "iat": now,
        "exp": now + settings.access_token_minutes * 60,
    }
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = f"{_b64_json(header)}.{_b64_json(body)}"
    signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        signing_input.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_b64(signature)}"


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}"
        expected = hmac.new(
            settings.jwt_secret_key.encode("utf-8"),
            signing_input.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_b64(expected), signature_b64):
            raise ValueError("invalid signature")
        payload = json.loads(_b64_decode(payload_b64))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    return payload


def get_token_payload(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return decode_access_token(credentials.credentials)


def require_admin(payload: dict[str, Any] = Depends(get_token_payload)) -> dict[str, Any]:
    if not is_admin_role(str(payload.get("role", ""))):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return payload


def require_system_admin(payload: dict[str, Any] = Depends(get_token_payload)) -> dict[str, Any]:
    if normalize_role(str(payload.get("role", ""))) != "system_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System admin role required")
    return payload


def _b64_json(data: dict[str, Any]) -> str:
    return _b64(json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
