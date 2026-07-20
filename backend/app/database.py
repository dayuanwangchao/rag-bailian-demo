"""Shared database access for the cloud deployment.

PostgreSQL is the production store.  SQLite remains an intentionally small
test/local fallback so the API can be exercised without Docker services.
"""
import json
import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from .config import DATA_DIR, get_settings
from .security import hash_password

ENTERPRISE_ROLES = {"system_admin", "kb_admin", "editor", "reader"}
ADMIN_ROLES = {"system_admin", "kb_admin", "editor", "admin"}


class Cursor:
    def __init__(self, cursor, lastrowid: int | None = None):
        self._cursor = cursor
        self.lastrowid = lastrowid if lastrowid is not None else getattr(cursor, "lastrowid", None)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)


class Connection:
    """DB-API subset with SQLite-style placeholders used by the application."""
    def __init__(self, raw, postgres: bool):
        self.raw, self.postgres = raw, postgres

    def execute(self, query: str, params: Any = ()) -> Cursor:
        if not self.postgres:
            return Cursor(self.raw.execute(query, params))
        sql = query.replace("?", "%s")
        sql = re.sub(r"INSERT OR REPLACE INTO (\w+)", r"INSERT INTO \1", sql, flags=re.I)
        if "INSERT OR REPLACE" in query:
            sql += " ON CONFLICT (chunk_id) DO UPDATE SET model = EXCLUDED.model, dimensions = EXCLUDED.dimensions"
        is_insert = sql.lstrip().upper().startswith("INSERT")
        if is_insert and "RETURNING" not in sql.upper():
            sql = sql.rstrip().rstrip(";") + " RETURNING id"
        cur = self.raw.cursor()
        cur.execute(sql, params)
        lastrowid = None
        if is_insert:
            row = cur.fetchone()
            lastrowid = int(row["id"]) if row else None
        return Cursor(cur, lastrowid)

    def executescript(self, script: str) -> None:
        if self.postgres:
            for statement in (part.strip() for part in script.split(";") if part.strip()):
                self.execute(statement)
        else:
            self.raw.executescript(script)


@contextmanager
def get_db() -> Iterator[Connection]:
    settings = get_settings()
    postgres = settings.database_url.startswith("postgresql")
    if postgres:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # clearer than silently switching production to SQLite
            raise RuntimeError("PostgreSQL deployment requires psycopg[binary]") from exc
        raw = psycopg.connect(settings.database_url, row_factory=dict_row)
    else:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(DATA_DIR / "rag.db")
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
    conn = Connection(raw, postgres)
    try:
        yield conn
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def init_db() -> None:
    with get_db() as conn:
        if conn.postgres:
            user_columns = {
                row["column_name"]
                for row in conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='users'"
                ).fetchall()
            }
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.executescript(_POSTGRES_SCHEMA)
            if "clearance_level" not in user_columns:
                conn.execute(
                    """
                    UPDATE users SET clearance_level = CASE
                        WHEN role = 'system_admin' THEN 3
                        WHEN role IN ('kb_admin', 'editor') THEN 2
                        ELSE 1 END
                    """
                )
        else:
            user_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()
            }
            document_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(documents)").fetchall()
            }
            conn.executescript(_SQLITE_SCHEMA)
            chunk_columns = {row["name"] for row in conn.execute("PRAGMA table_info(chunks)").fetchall()}
            current_user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
            current_document_columns = {row["name"] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
            if "embedding" not in chunk_columns:
                conn.execute("ALTER TABLE chunks ADD COLUMN embedding TEXT")
            if "clearance_level" not in current_user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN clearance_level INTEGER NOT NULL DEFAULT 1")
            if "clearance_level" not in user_columns:
                conn.execute(
                    "UPDATE users SET clearance_level = CASE WHEN role='system_admin' THEN 3 WHEN role IN ('kb_admin','editor') THEN 2 ELSE 1 END"
                )
            if "security_level" not in current_document_columns:
                conn.execute("ALTER TABLE documents ADD COLUMN security_level INTEGER NOT NULL DEFAULT 1")
        _seed_enterprise_defaults(conn)


_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS departments (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, role TEXT NOT NULL, department_id INTEGER, position TEXT NOT NULL DEFAULT '', clearance_level INTEGER NOT NULL DEFAULT 1 CHECK(clearance_level BETWEEN 0 AND 3), status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_login_at TEXT);
CREATE TABLE IF NOT EXISTS knowledge_bases (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, description TEXT NOT NULL DEFAULT '', owner_id INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY AUTOINCREMENT, knowledge_base_id INTEGER NOT NULL DEFAULT 1, file_name TEXT NOT NULL, file_path TEXT NOT NULL, file_uri TEXT NOT NULL DEFAULT '', file_hash TEXT NOT NULL DEFAULT '', file_type TEXT NOT NULL, size INTEGER NOT NULL, uploaded_by INTEGER, uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, status TEXT NOT NULL DEFAULT 'pending', chunks INTEGER NOT NULL DEFAULT 0, current_version INTEGER NOT NULL DEFAULT 1, department_scope TEXT NOT NULL DEFAULT '[]', visible_roles TEXT NOT NULL DEFAULT '[]', visible_users TEXT NOT NULL DEFAULT '[]', classification TEXT NOT NULL DEFAULT 'internal', security_level INTEGER NOT NULL DEFAULT 1 CHECK(security_level BETWEEN 0 AND 3), archived_at TEXT, error_message TEXT);
CREATE TABLE IF NOT EXISTS document_versions (id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER NOT NULL, version INTEGER NOT NULL, file_uri TEXT NOT NULL, file_hash TEXT NOT NULL, size INTEGER NOT NULL, created_by INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(document_id, version));
CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER NOT NULL, document_version_id INTEGER, file_name TEXT NOT NULL, chunk_id INTEGER NOT NULL, section_title TEXT NOT NULL DEFAULT '', page_start INTEGER, page_end INTEGER, token_count INTEGER NOT NULL DEFAULT 0, content_hash TEXT NOT NULL DEFAULT '', content TEXT NOT NULL, permission_tags TEXT NOT NULL DEFAULT '[]', embedding TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS chunk_embeddings (chunk_id INTEGER PRIMARY KEY, model TEXT NOT NULL, dimensions INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS ingestion_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending', progress INTEGER NOT NULL DEFAULT 0, retry_count INTEGER NOT NULL DEFAULT 0, error_message TEXT, log_summary TEXT NOT NULL DEFAULT '', started_at TEXT, finished_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS chat_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, knowledge_base_id INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS chat_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, user_id INTEGER NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL, sources_json TEXT NOT NULL, retrieval_count INTEGER NOT NULL DEFAULT 0, refused INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER, action TEXT NOT NULL, target_type TEXT NOT NULL DEFAULT '', target_id TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER, user_id INTEGER NOT NULL, rating TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""

_POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS departments (id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS users (id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('system_admin','kb_admin','editor','reader')), department_id BIGINT REFERENCES departments(id), position TEXT NOT NULL DEFAULT '', clearance_level INTEGER NOT NULL DEFAULT 1 CHECK(clearance_level BETWEEN 0 AND 3), status TEXT NOT NULL DEFAULT 'active', created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, last_login_at TIMESTAMPTZ);
ALTER TABLE users ADD COLUMN IF NOT EXISTS clearance_level INTEGER NOT NULL DEFAULT 1 CHECK(clearance_level BETWEEN 0 AND 3);
CREATE TABLE IF NOT EXISTS knowledge_bases (id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT NOT NULL DEFAULT '', owner_id BIGINT REFERENCES users(id), created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS documents (id BIGSERIAL PRIMARY KEY, knowledge_base_id BIGINT NOT NULL DEFAULT 1 REFERENCES knowledge_bases(id), file_name TEXT NOT NULL, file_path TEXT NOT NULL, file_uri TEXT NOT NULL DEFAULT '', file_hash TEXT NOT NULL DEFAULT '', file_type TEXT NOT NULL, size BIGINT NOT NULL, uploaded_by BIGINT REFERENCES users(id), uploaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, status TEXT NOT NULL DEFAULT 'pending', chunks INTEGER NOT NULL DEFAULT 0, current_version INTEGER NOT NULL DEFAULT 1, department_scope JSONB NOT NULL DEFAULT '[]', visible_roles JSONB NOT NULL DEFAULT '[]', visible_users JSONB NOT NULL DEFAULT '[]', classification TEXT NOT NULL DEFAULT 'internal', security_level INTEGER NOT NULL DEFAULT 1 CHECK(security_level BETWEEN 0 AND 3), archived_at TIMESTAMPTZ, error_message TEXT);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS security_level INTEGER NOT NULL DEFAULT 1 CHECK(security_level BETWEEN 0 AND 3);
CREATE TABLE IF NOT EXISTS document_versions (id BIGSERIAL PRIMARY KEY, document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE, version INTEGER NOT NULL, file_uri TEXT NOT NULL, file_hash TEXT NOT NULL, size BIGINT NOT NULL, created_by BIGINT REFERENCES users(id), created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(document_id, version));
CREATE TABLE IF NOT EXISTS chunks (id BIGSERIAL PRIMARY KEY, document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE, document_version_id BIGINT REFERENCES document_versions(id) ON DELETE SET NULL, file_name TEXT NOT NULL, chunk_id INTEGER NOT NULL, section_title TEXT NOT NULL DEFAULT '', page_start INTEGER, page_end INTEGER, token_count INTEGER NOT NULL DEFAULT 0, content_hash TEXT NOT NULL DEFAULT '', content TEXT NOT NULL, permission_tags JSONB NOT NULL DEFAULT '[]', embedding vector(1024), created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP);
ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1024) USING embedding::vector(1024);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE TABLE IF NOT EXISTS ingestion_jobs (id BIGSERIAL PRIMARY KEY, document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE, status TEXT NOT NULL DEFAULT 'pending', progress INTEGER NOT NULL DEFAULT 0, retry_count INTEGER NOT NULL DEFAULT 0, error_message TEXT, log_summary TEXT NOT NULL DEFAULT '', started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS chat_sessions (id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id), knowledge_base_id BIGINT REFERENCES knowledge_bases(id), created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS chat_messages (id BIGSERIAL PRIMARY KEY, session_id BIGINT REFERENCES chat_sessions(id) ON DELETE SET NULL, user_id BIGINT NOT NULL REFERENCES users(id), question TEXT NOT NULL, answer TEXT NOT NULL, sources_json JSONB NOT NULL DEFAULT '[]', retrieval_count INTEGER NOT NULL DEFAULT 0, refused BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit_logs (id BIGSERIAL PRIMARY KEY, actor_id BIGINT REFERENCES users(id), action TEXT NOT NULL, target_type TEXT NOT NULL DEFAULT '', target_id TEXT NOT NULL DEFAULT '', metadata_json JSONB NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS feedback (id BIGSERIAL PRIMARY KEY, message_id BIGINT REFERENCES chat_messages(id) ON DELETE SET NULL, user_id BIGINT NOT NULL REFERENCES users(id), rating TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""


def _seed_enterprise_defaults(conn: Connection) -> None:
    if conn.postgres:
        conn.execute("INSERT INTO departments (id, name) VALUES (1, '总部') ON CONFLICT (id) DO NOTHING")
        conn.execute("INSERT INTO departments (id, name) VALUES (2, '研发部') ON CONFLICT (id) DO NOTHING")
        conn.execute("INSERT INTO departments (id, name) VALUES (3, '运营部') ON CONFLICT (id) DO NOTHING")
        conn.execute("INSERT INTO knowledge_bases (id, name, description) VALUES (1, '默认知识库', '企业知识库试点空间') ON CONFLICT (id) DO NOTHING")
        conn.execute("SELECT setval(pg_get_serial_sequence('departments','id'), COALESCE((SELECT MAX(id) FROM departments), 1), true)")
        conn.execute("SELECT setval(pg_get_serial_sequence('knowledge_bases','id'), COALESCE((SELECT MAX(id) FROM knowledge_bases), 1), true)")
    else:
        for ident, name in ((1, '总部'), (2, '研发部'), (3, '运营部')):
            conn.execute("INSERT OR IGNORE INTO departments (id, name) VALUES (?, ?)", (ident, name))
        conn.execute("INSERT OR IGNORE INTO knowledge_bases (id, name, description) VALUES (1, '默认知识库', '企业知识库试点空间')")
    for username, password, role, department, position, clearance_level in (
        ('admin','admin123','system_admin',1,'系统管理员',3), ('kbadmin','kbadmin123','kb_admin',2,'知识库管理员',2), ('editor','editor123','editor',2,'知识库编辑',2), ('user','user123','reader',1,'普通员工',1),
    ):
        if conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone() is None:
            conn.execute("INSERT INTO users (username, password_hash, role, department_id, position, clearance_level) VALUES (?, ?, ?, ?, ?, ?)", (username, hash_password(password), role, department, position, clearance_level))


def get_user_by_username(username: str):
    with get_db() as conn: return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
def get_user_by_id(user_id: int):
    with get_db() as conn: return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
def list_departments() -> list[dict[str, Any]]:
    with get_db() as conn: return [dict(row) for row in conn.execute("SELECT id, name, created_at FROM departments ORDER BY id").fetchall()]
def list_users() -> list[dict[str, Any]]:
    with get_db() as conn: return [dict(row) for row in conn.execute("SELECT u.id,u.username,u.role,u.department_id,d.name AS department_name,u.position,u.clearance_level,u.status,u.created_at,u.last_login_at FROM users u LEFT JOIN departments d ON d.id=u.department_id ORDER BY u.id").fetchall()]
def create_user(username: str, password: str, role: str, department_id: int | None, position: str, clearance_level: int, actor_id: int) -> dict[str, Any]:
    with get_db() as conn:
        if department_id is not None and conn.execute("SELECT id FROM departments WHERE id = ?", (department_id,)).fetchone() is None: raise ValueError("部门不存在")
        user_id = int(conn.execute("INSERT INTO users (username,password_hash,role,department_id,position,clearance_level) VALUES (?,?,?,?,?,?)", (username,hash_password(password),role,department_id,position,clearance_level)).lastrowid)
    audit(actor_id,"user.create","user",user_id,{"username":username,"role":role,"clearance_level":clearance_level}); return dict(get_user_by_id(user_id) or {})
def update_user(user_id: int, updates: dict[str, Any], actor_id: int) -> dict[str, Any] | None:
    allowed={k:v for k,v in updates.items() if v is not None and k in {"role","department_id","position","clearance_level","status"}}
    if user_id == actor_id and "status" in allowed: raise ValueError("不能修改当前登录账号状态")
    if user_id == actor_id and allowed.get("role") and normalize_role(allowed["role"]) != "system_admin": raise ValueError("不能降低当前登录账号权限")
    with get_db() as conn:
        existing=conn.execute("SELECT id,role,status FROM users WHERE id=?",(user_id,)).fetchone()
        if existing is None: return None
        if normalize_role(existing["role"]) == "system_admin" and (allowed.get("status")=="disabled" or allowed.get("role") not in (None,"system_admin")):
            if int(conn.execute("SELECT COUNT(*) AS count FROM users WHERE role='system_admin' AND status='active'").fetchone()["count"]) <= 1: raise ValueError("至少需要保留一个启用状态的系统管理员")
        if allowed:
            conn.execute("UPDATE users SET " + ", ".join(f"{key} = ?" for key in allowed) + " WHERE id = ?", (*allowed.values(),user_id))
    audit(actor_id,"user.update","user",user_id,allowed); user=get_user_by_id(user_id); return dict(user) if user else None
def touch_last_login(user_id: int) -> None:
    with get_db() as conn: conn.execute("UPDATE users SET last_login_at=CURRENT_TIMESTAMP WHERE id=?",(user_id,))
def normalize_role(role: str) -> str: return {"admin":"system_admin","user":"reader"}.get(role,role)
def is_admin_role(role: str) -> bool: return normalize_role(role) in ADMIN_ROLES
def audit(actor_id: int | None, action: str, target_type: str="", target_id: Any="", metadata: dict[str,Any] | None=None) -> None:
    with get_db() as conn: conn.execute("INSERT INTO audit_logs (actor_id,action,target_type,target_id,metadata_json) VALUES (?,?,?,?,?)",(actor_id,action,target_type,str(target_id),json.dumps(metadata or {},ensure_ascii=False)))
def migrate_json_runtime_data() -> None:
    """Legacy JSON import was superseded by the explicit SQLite migration command."""
