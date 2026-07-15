import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import DATA_DIR, INDEX_DIR
from .security import hash_password


DB_PATH = DATA_DIR / "rag.db"
ENTERPRISE_ROLES = {"system_admin", "kb_admin", "editor", "reader"}
ADMIN_ROLES = {"system_admin", "kb_admin", "editor", "admin"}


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        _migrate_legacy_users(conn)
        _migrate_legacy_documents(conn)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('system_admin', 'kb_admin', 'editor', 'reader')),
                department_id INTEGER,
                position TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_login_at TEXT,
                FOREIGN KEY(department_id) REFERENCES departments(id)
            );

            CREATE TABLE IF NOT EXISTS knowledge_bases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                owner_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(owner_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                knowledge_base_id INTEGER NOT NULL DEFAULT 1,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_uri TEXT NOT NULL DEFAULT '',
                file_hash TEXT NOT NULL DEFAULT '',
                file_type TEXT NOT NULL,
                size INTEGER NOT NULL,
                uploaded_by INTEGER,
                uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'pending',
                chunks INTEGER NOT NULL DEFAULT 0,
                current_version INTEGER NOT NULL DEFAULT 1,
                department_scope TEXT NOT NULL DEFAULT '[]',
                visible_roles TEXT NOT NULL DEFAULT '["reader","editor","kb_admin","system_admin"]',
                visible_users TEXT NOT NULL DEFAULT '[]',
                classification TEXT NOT NULL DEFAULT 'internal',
                expires_at TEXT,
                archived_at TEXT,
                error_message TEXT,
                FOREIGN KEY(knowledge_base_id) REFERENCES knowledge_bases(id),
                FOREIGN KEY(uploaded_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS document_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                version INTEGER NOT NULL,
                file_uri TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                size INTEGER NOT NULL,
                created_by INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(document_id, version),
                FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY(created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                document_version_id INTEGER,
                file_name TEXT NOT NULL,
                chunk_id INTEGER NOT NULL,
                section_title TEXT NOT NULL DEFAULT '',
                page_start INTEGER,
                page_end INTEGER,
                token_count INTEGER NOT NULL DEFAULT 0,
                content_hash TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                permission_tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY(document_version_id) REFERENCES document_versions(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS chunk_embeddings (
                chunk_id INTEGER PRIMARY KEY,
                model TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ingestion_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                progress INTEGER NOT NULL DEFAULT 0,
                retry_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                log_summary TEXT NOT NULL DEFAULT '',
                started_at TEXT,
                finished_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                knowledge_base_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(knowledge_base_id) REFERENCES knowledge_bases(id)
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                user_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                retrieval_count INTEGER NOT NULL DEFAULT 0,
                refused INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id INTEGER,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL DEFAULT '',
                target_id TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(actor_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER,
                user_id INTEGER NOT NULL,
                rating TEXT NOT NULL,
                comment TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(message_id) REFERENCES chat_messages(id) ON DELETE SET NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )
        _add_missing_columns(conn)
        _repair_legacy_chunk_foreign_key(conn)
        _seed_enterprise_defaults(conn)


def _migrate_legacy_users(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'users'").fetchone()
    if row is None or "system_admin" in (row["sql"] or ""):
        return
    conn.execute("ALTER TABLE users RENAME TO users_legacy")
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('system_admin', 'kb_admin', 'editor', 'reader')),
            department_id INTEGER,
            position TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_login_at TEXT,
            FOREIGN KEY(department_id) REFERENCES departments(id)
        );
        """
    )
    rows = conn.execute("SELECT * FROM users_legacy").fetchall()
    for user in rows:
        role = "system_admin" if user["role"] == "admin" else "reader"
        conn.execute(
            """
            INSERT INTO users (id, username, password_hash, role, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user["id"], user["username"], user["password_hash"], role, user["created_at"]),
        )
    conn.execute("DROP TABLE users_legacy")


def _migrate_legacy_documents(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'documents'").fetchone()
    if row is None or "knowledge_base_id" in (row["sql"] or ""):
        return
    conn.execute("ALTER TABLE documents RENAME TO documents_legacy")
    conn.executescript(
        """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_base_id INTEGER NOT NULL DEFAULT 1,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_uri TEXT NOT NULL DEFAULT '',
            file_hash TEXT NOT NULL DEFAULT '',
            file_type TEXT NOT NULL,
            size INTEGER NOT NULL,
            uploaded_by INTEGER,
            uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'pending',
            chunks INTEGER NOT NULL DEFAULT 0,
            current_version INTEGER NOT NULL DEFAULT 1,
            department_scope TEXT NOT NULL DEFAULT '[]',
            visible_roles TEXT NOT NULL DEFAULT '["reader","editor","kb_admin","system_admin"]',
            visible_users TEXT NOT NULL DEFAULT '[]',
            classification TEXT NOT NULL DEFAULT 'internal',
            expires_at TEXT,
            archived_at TEXT,
            error_message TEXT
        );
        """
    )
    rows = conn.execute("SELECT * FROM documents_legacy").fetchall()
    for doc in rows:
        conn.execute(
            """
            INSERT INTO documents
            (id, file_name, file_path, file_uri, file_type, size, uploaded_by, uploaded_at, status, chunks, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc["id"],
                doc["file_name"],
                doc["file_path"],
                doc["file_path"],
                doc["file_type"],
                doc["size"],
                doc["uploaded_by"],
                doc["uploaded_at"],
                doc["status"],
                doc["chunks"],
                doc["error_message"],
            ),
        )
    if conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'chunks'").fetchone():
        conn.execute("DELETE FROM chunks")
    conn.execute("DROP TABLE documents_legacy")


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    def add(table: str, column: str, ddl: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    if conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'chunks'").fetchone():
        add("chunks", "document_version_id", "document_version_id INTEGER")
        add("chunks", "section_title", "section_title TEXT NOT NULL DEFAULT ''")
        add("chunks", "page_start", "page_start INTEGER")
        add("chunks", "page_end", "page_end INTEGER")
        add("chunks", "token_count", "token_count INTEGER NOT NULL DEFAULT 0")
        add("chunks", "content_hash", "content_hash TEXT NOT NULL DEFAULT ''")
        add("chunks", "permission_tags", "permission_tags TEXT NOT NULL DEFAULT '[]'")


def _repair_legacy_chunk_foreign_key(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'chunks'").fetchone()
    if row is None or "documents_legacy" not in (row["sql"] or ""):
        return

    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript(
        """
        CREATE TEMP TABLE chunk_embeddings_backup AS
        SELECT ce.*
        FROM chunk_embeddings ce
        JOIN chunks c ON c.id = ce.chunk_id
        JOIN documents d ON d.id = c.document_id;

        DROP TABLE IF EXISTS chunk_embeddings;
        ALTER TABLE chunks RENAME TO chunks_legacy_fk;

        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            document_version_id INTEGER,
            file_name TEXT NOT NULL,
            chunk_id INTEGER NOT NULL,
            section_title TEXT NOT NULL DEFAULT '',
            page_start INTEGER,
            page_end INTEGER,
            token_count INTEGER NOT NULL DEFAULT 0,
            content_hash TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            permission_tags TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
            FOREIGN KEY(document_version_id) REFERENCES document_versions(id) ON DELETE SET NULL
        );

        INSERT INTO chunks
        (id, document_id, document_version_id, file_name, chunk_id, section_title, page_start, page_end,
         token_count, content_hash, content, permission_tags, created_at)
        SELECT c.id, c.document_id, c.document_version_id, c.file_name, c.chunk_id,
               COALESCE(c.section_title, ''), c.page_start, c.page_end, COALESCE(c.token_count, 0),
               COALESCE(c.content_hash, ''), c.content, COALESCE(c.permission_tags, '[]'), c.created_at
        FROM chunks_legacy_fk c
        JOIN documents d ON d.id = c.document_id;

        DROP TABLE chunks_legacy_fk;

        CREATE TABLE chunk_embeddings (
            chunk_id INTEGER PRIMARY KEY,
            model TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
        );

        INSERT INTO chunk_embeddings (chunk_id, model, dimensions, created_at)
        SELECT b.chunk_id, b.model, b.dimensions, b.created_at
        FROM chunk_embeddings_backup b
        JOIN chunks c ON c.id = b.chunk_id;

        DROP TABLE chunk_embeddings_backup;
        """
    )
    conn.execute("PRAGMA foreign_keys = ON")


def _seed_enterprise_defaults(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT OR IGNORE INTO departments (id, name) VALUES (1, '总部')")
    conn.execute("INSERT OR IGNORE INTO departments (id, name) VALUES (2, '研发部')")
    conn.execute("INSERT OR IGNORE INTO departments (id, name) VALUES (3, '运营部')")
    conn.execute(
        """
        INSERT OR IGNORE INTO knowledge_bases (id, name, description)
        VALUES (1, '默认知识库', '企业知识库试点空间')
        """
    )
    _seed_user(conn, "admin", "admin123", "system_admin", department_id=1, position="系统管理员")
    _seed_user(conn, "kbadmin", "kbadmin123", "kb_admin", department_id=2, position="知识库管理员")
    _seed_user(conn, "editor", "editor123", "editor", department_id=2, position="知识库编辑")
    _seed_user(conn, "user", "user123", "reader", department_id=1, position="普通员工")


def migrate_json_runtime_data() -> None:
    documents_path = INDEX_DIR / "documents.json"
    history_path = INDEX_DIR / "history.json"
    marker_path = INDEX_DIR / ".json_migrated"
    if marker_path.exists():
        return
    if not documents_path.exists() and not history_path.exists():
        marker_path.write_text("ok", encoding="utf-8")
        return

    with get_db() as conn:
        admin = get_user_by_username("admin")
        admin_id = int(admin["id"]) if admin else None
        if documents_path.exists() and conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0:
            for item in _read_json_list(documents_path):
                file_name = item.get("file_name", "")
                if not file_name:
                    continue
                upload_path = DATA_DIR / "uploads" / file_name
                conn.execute(
                    """
                    INSERT OR IGNORE INTO documents
                    (knowledge_base_id, file_name, file_path, file_uri, file_type, size, uploaded_by, status, chunks)
                    VALUES (1, ?, ?, ?, ?, ?, ?, 'pending', 0)
                    """,
                    (
                        file_name,
                        str(upload_path),
                        str(upload_path),
                        Path(file_name).suffix.lower().lstrip("."),
                        int(item.get("size", 0)),
                        admin_id,
                    ),
                )
        if history_path.exists() and conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 0:
            user = get_user_by_username("user")
            user_id = int(user["id"]) if user else 1
            for row in _read_json_list(history_path):
                conn.execute(
                    """
                    INSERT INTO chat_messages (user_id, question, answer, sources_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        row.get("question", ""),
                        row.get("answer", ""),
                        json.dumps(row.get("sources", []), ensure_ascii=False),
                    ),
                )
    marker_path.write_text("ok", encoding="utf-8")


def get_user_by_username(username: str) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def list_departments() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT id, name, created_at FROM departments ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def list_users() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT u.id, u.username, u.role, u.department_id, d.name AS department_name,
                   u.position, u.status, u.created_at, u.last_login_at
            FROM users u
            LEFT JOIN departments d ON d.id = u.department_id
            ORDER BY u.id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def create_user(
    username: str,
    password: str,
    role: str,
    department_id: int | None,
    position: str,
    actor_id: int,
) -> dict[str, Any]:
    with get_db() as conn:
        if department_id is not None:
            department = conn.execute("SELECT id FROM departments WHERE id = ?", (department_id,)).fetchone()
            if department is None:
                raise ValueError("部门不存在")
        cursor = conn.execute(
            """
            INSERT INTO users (username, password_hash, role, department_id, position)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, hash_password(password), role, department_id, position),
        )
        user_id = int(cursor.lastrowid)
    audit(actor_id, "user.create", "user", user_id, {"username": username, "role": role})
    user = get_user_by_id(user_id)
    return dict(user) if user else {}


def update_user(user_id: int, updates: dict[str, Any], actor_id: int) -> dict[str, Any] | None:
    allowed = {key: value for key, value in updates.items() if value is not None and key in {"role", "department_id", "position", "status"}}
    if not allowed:
        user = get_user_by_id(user_id)
        return dict(user) if user else None
    if user_id == actor_id and "status" in allowed:
        raise ValueError("不能修改当前登录账号状态")
    if user_id == actor_id and allowed.get("role") and normalize_role(allowed["role"]) != "system_admin":
        raise ValueError("不能降低当前登录账号权限")
    with get_db() as conn:
        existing = conn.execute("SELECT id, role, status FROM users WHERE id = ?", (user_id,)).fetchone()
        if existing is None:
            return None
        current_role = normalize_role(existing["role"])
        will_disable = allowed.get("status") == "disabled"
        will_remove_system_admin = allowed.get("role") and normalize_role(allowed["role"]) != "system_admin"
        if current_role == "system_admin" and (will_disable or will_remove_system_admin):
            active_admins = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'system_admin' AND status = 'active'"
            ).fetchone()[0]
            if int(active_admins) <= 1:
                raise ValueError("至少需要保留一个启用状态的系统管理员")
        if allowed.get("department_id") is not None:
            department = conn.execute("SELECT id FROM departments WHERE id = ?", (allowed["department_id"],)).fetchone()
            if department is None:
                raise ValueError("部门不存在")
        assignments = ", ".join(f"{key} = ?" for key in allowed)
        conn.execute(
            f"UPDATE users SET {assignments} WHERE id = ?",
            [*allowed.values(), user_id],
        )
    audit(actor_id, "user.update", "user", user_id, allowed)
    user = get_user_by_id(user_id)
    return dict(user) if user else None


def touch_last_login(user_id: int) -> None:
    with get_db() as conn:
        conn.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def normalize_role(role: str) -> str:
    if role == "admin":
        return "system_admin"
    if role == "user":
        return "reader"
    return role


def is_admin_role(role: str) -> bool:
    return normalize_role(role) in ADMIN_ROLES


def audit(actor_id: int | None, action: str, target_type: str = "", target_id: Any = "", metadata: dict[str, Any] | None = None) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO audit_logs (actor_id, action, target_type, target_id, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (actor_id, action, target_type, str(target_id), json.dumps(metadata or {}, ensure_ascii=False)),
        )


def _seed_user(
    conn: sqlite3.Connection,
    username: str,
    password: str,
    role: str,
    department_id: int | None = None,
    position: str = "",
) -> None:
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE users
            SET role = CASE WHEN role IN ('admin', 'user') THEN ? ELSE role END,
                department_id = COALESCE(department_id, ?),
                position = CASE WHEN position = '' THEN ? ELSE position END,
                status = 'active'
            WHERE id = ?
            """,
            (role, department_id, position, existing["id"]),
        )
        return
    conn.execute(
        """
        INSERT INTO users (username, password_hash, role, department_id, position)
        VALUES (?, ?, ?, ?, ?)
        """,
        (username, hash_password(password), role, department_id, position),
    )


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
