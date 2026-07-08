import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import DATA_DIR, INDEX_DIR
from .security import hash_password


DB_PATH = DATA_DIR / "rag.db"


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT NOT NULL UNIQUE,
                file_path TEXT NOT NULL,
                file_type TEXT NOT NULL,
                size INTEGER NOT NULL,
                uploaded_by INTEGER,
                uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'pending',
                chunks INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                FOREIGN KEY(uploaded_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                chunk_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )
        _seed_user(conn, "admin", "admin123", "admin")
        _seed_user(conn, "user", "user123", "user")


def migrate_json_runtime_data() -> None:
    """Best-effort migration from the first demo's JSON files into SQLite."""
    documents_path = INDEX_DIR / "documents.json"
    history_path = INDEX_DIR / "history.json"
    if not documents_path.exists() and not history_path.exists():
        return

    with get_db() as conn:
        admin_id = get_user_by_username("admin")["id"]
        if documents_path.exists() and conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0:
            for item in _read_json_list(documents_path):
                file_name = item.get("file_name", "")
                if not file_name:
                    continue
                upload_path = DATA_DIR / "uploads" / file_name
                conn.execute(
                    """
                    INSERT OR IGNORE INTO documents
                    (file_name, file_path, file_type, size, uploaded_by, status, chunks)
                    VALUES (?, ?, ?, ?, ?, 'pending', 0)
                    """,
                    (
                        file_name,
                        str(upload_path),
                        Path(file_name).suffix.lower().lstrip("."),
                        int(item.get("size", 0)),
                        admin_id,
                    ),
                )
        if history_path.exists() and conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0] == 0:
            user_id = get_user_by_username("user")["id"]
            for row in _read_json_list(history_path):
                conn.execute(
                    """
                    INSERT INTO chat_history (user_id, question, answer, sources_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        row.get("question", ""),
                        row.get("answer", ""),
                        json.dumps(row.get("sources", []), ensure_ascii=False),
                    ),
                )


def get_user_by_username(username: str) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _seed_user(conn: sqlite3.Connection, username: str, password: str, role: str) -> None:
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        return
    conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username, hash_password(password), role),
    )


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
