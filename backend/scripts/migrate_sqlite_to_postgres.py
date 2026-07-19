"""One-time migration from the legacy SQLite demo to cloud storage.

Run with DATABASE_URL pointing at PostgreSQL/pgvector and with Redis/MinIO
available. Existing vector files are deliberately not copied: documents are
queued for a clean embedding rebuild using the configured embedding model.
"""
import argparse
import hashlib
import sqlite3
import sys
from pathlib import Path

# Running a script makes ``scripts`` the import root; add the backend package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import get_db, init_db
from app.object_storage import object_storage
from app.queue import enqueue_ingestion
from app.rag import create_ingestion_job


TABLES = ("departments", "users", "knowledge_bases", "documents", "chat_sessions", "chat_messages", "audit_logs", "feedback")


def copy_metadata(source: sqlite3.Connection) -> list[int]:
    document_ids: list[int] = []
    with get_db() as target:
        if not target.postgres:
            raise RuntimeError("Set DATABASE_URL to the PostgreSQL target before running this migration")
        for table in TABLES:
            if source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is None:
                continue
            rows = source.execute(f"SELECT * FROM {table}").fetchall()
            target_columns = {
                row["column_name"]
                for row in target.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = ?",
                    (table,),
                ).fetchall()
            }
            for row in rows:
                values = {key: value for key, value in dict(row).items() if key in target_columns}
                columns = list(values)
                # File object keys are filled in after the metadata pass.
                if table == "documents":
                    document_ids.append(int(values["id"]))
                    values["status"], values["chunks"], values["error_message"] = "pending", 0, None
                if table == "chat_messages" and "refused" in values:
                    values["refused"] = bool(values["refused"])
                placeholders = ", ".join("?" for _ in columns)
                target.execute(
                    f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING",
                    tuple(values[column] for column in columns),
                )
        for table in TABLES:
            target.execute(
                "SELECT setval(pg_get_serial_sequence(?, 'id'), COALESCE((SELECT MAX(id) FROM " + table + "), 1), true)",
                (table,),
            )
    return document_ids


def move_files(source_path: Path, document_ids: list[int]) -> None:
    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    try:
        for document_id in document_ids:
            row = source.execute("SELECT file_name, file_path FROM documents WHERE id=?", (document_id,)).fetchone()
            if not row:
                continue
            legacy_path = Path(row["file_path"])
            if not legacy_path.exists():
                legacy_path = source_path.parent / "uploads" / row["file_path"]
            if not legacy_path.exists():
                legacy_path = source_path.parent / "uploads" / row["file_name"]
            if not legacy_path.exists():
                print(f"skip missing file: {legacy_path}")
                continue
            data = legacy_path.read_bytes()
            key, digest = object_storage.put_bytes(row["file_name"], data)
            with get_db() as target:
                target.execute("UPDATE documents SET file_path=?, file_uri=?, file_hash=? WHERE id=?", (key, key, digest or hashlib.sha256(data).hexdigest(), document_id))
            enqueue_ingestion(create_ingestion_job(document_id))
    finally:
        source.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sqlite_db", type=Path, help="Path to legacy data/rag.db")
    args = parser.parse_args()
    source = sqlite3.connect(args.sqlite_db)
    source.row_factory = sqlite3.Row
    try:
        init_db()
        document_ids = copy_metadata(source)
    finally:
        source.close()
    move_files(args.sqlite_db, document_ids)
    print(f"Migrated metadata and queued {len(document_ids)} documents for re-indexing")


if __name__ == "__main__":
    main()
