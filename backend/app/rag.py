import json
import re
from pathlib import Path
from typing import Any

from .config import UPLOAD_DIR, get_settings
from .database import get_db
from .document_loader import load_document
from .embeddings import embed_texts
from .llm import chat_completion
from .schemas import Source
from .splitter import split_text
from .vector_store import vector_store


SYSTEM_PROMPT = """你是企业知识库问答助手。请严格基于回答用户问题。
如果资料中没有答案，请说“根据当前知识库资料，无法确定答案”，不要编造。
回答要结构清晰，必要时使用列表。
每个关键结论后标注引用，例如：[来源1]、[来源2]。"""


def build_messages(question: str, sources: list[Source]) -> list[dict[str, str]]:
    context = "\n\n".join(
        f"[来源{i}] 文件名：{source.file_name}；分块序号：{source.chunk_id}\n{source.content}"
        for i, source in enumerate(sources, start=1)
    )
    user_prompt = f"""知识库资料：
{context or "（无检索结果）"}

用户问题：
{question}

请基于以上资料作答，并在关键结论后标注对应来源。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def create_document_record(path: Path, user_id: int | None) -> int:
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM documents WHERE file_name = ?", (path.name,)).fetchone()
        if existing:
            document_id = int(existing["id"])
            chunk_rows = conn.execute("SELECT id FROM chunks WHERE document_id = ?", (document_id,)).fetchall()
            vector_store.remove([int(row["id"]) for row in chunk_rows])
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            conn.execute(
                """
                UPDATE documents
                SET file_path = ?, file_type = ?, size = ?, uploaded_by = ?, uploaded_at = CURRENT_TIMESTAMP,
                    status = 'pending', chunks = 0, error_message = NULL
                WHERE id = ?
                """,
                (str(path), path.suffix.lower().lstrip("."), path.stat().st_size, user_id, document_id),
            )
            return document_id

        cursor = conn.execute(
            """
            INSERT INTO documents (file_name, file_path, file_type, size, uploaded_by, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
            """,
            (path.name, str(path), path.suffix.lower().lstrip("."), path.stat().st_size, user_id),
        )
        return int(cursor.lastrowid)


async def index_document(document_id: int) -> None:
    with get_db() as conn:
        document = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if document is None:
            return
        conn.execute("UPDATE documents SET status = 'indexing', error_message = NULL WHERE id = ?", (document_id,))

    try:
        path = Path(document["file_path"])
        text = load_document(path)
        settings = get_settings()
        chunks = split_text(text, settings.chunk_size, settings.chunk_overlap)
        vectors = await embed_texts(chunks)

        with get_db() as conn:
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            chunk_ids: list[int] = []
            for i, chunk in enumerate(chunks, start=1):
                cursor = conn.execute(
                    """
                    INSERT INTO chunks (document_id, file_name, chunk_id, content)
                    VALUES (?, ?, ?, ?)
                    """,
                    (document_id, path.name, i, chunk),
                )
                chunk_ids.append(int(cursor.lastrowid))

        vector_store.add(vectors, chunk_ids)
        with get_db() as conn:
            conn.execute(
                "UPDATE documents SET status = 'indexed', chunks = ?, error_message = NULL WHERE id = ?",
                (len(chunks), document_id),
            )
    except Exception as exc:
        with get_db() as conn:
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            conn.execute(
                "UPDATE documents SET status = 'failed', chunks = 0, error_message = ? WHERE id = ?",
                (str(exc), document_id),
            )


async def rebuild_index() -> tuple[int, int]:
    vector_store.reset()
    with get_db() as conn:
        conn.execute("DELETE FROM chunks")
        conn.execute("UPDATE documents SET status = 'pending', chunks = 0, error_message = NULL")
        document_ids = [int(row["id"]) for row in conn.execute("SELECT id FROM documents ORDER BY id").fetchall()]

    for document_id in document_ids:
        await index_document(document_id)

    documents = list_documents()
    return len(documents), sum(int(doc["chunks"]) for doc in documents if doc["status"] == "indexed")


async def delete_document(document_id: int) -> bool:
    with get_db() as conn:
        document = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if document is None:
            return False
        chunk_ids = [int(row["id"]) for row in conn.execute("SELECT id FROM chunks WHERE document_id = ?", (document_id,))]
        conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    vector_store.remove(chunk_ids)
    path = Path(document["file_path"])
    if path.exists() and path.is_file() and UPLOAD_DIR in path.resolve().parents:
        path.unlink()
    return True


async def answer_question(question: str, user_id: int, top_k: int | None = None) -> tuple[str, list[Source]]:
    sources = await retrieve_sources(question, top_k)
    if not sources:
        answer = "根据当前知识库资料，无法确定答案。"
    else:
        answer = await chat_completion(build_messages(question, sources))
        sources = filter_cited_sources(answer, sources)
    append_history(user_id, question, answer, sources)
    return answer, sources


def filter_cited_sources(answer: str, sources: list[Source]) -> list[Source]:
    cited_ids = {int(match) for match in re.findall(r"\[来源(\d+)\]", answer)}
    if not cited_ids:
        return sources[:1] if len(sources) == 1 else sources
    return [source for source in sources if source.id in cited_ids]


async def retrieve_sources(question: str, top_k: int | None = None) -> list[Source]:
    settings = get_settings()
    query_vector = (await embed_texts([question]))[0]
    results = vector_store.search(query_vector, top_k or settings.top_k)
    filtered_ids = [(chunk_id, score) for chunk_id, score in results if score >= settings.similarity_threshold]
    if not filtered_ids:
        return []

    scores = {chunk_id: score for chunk_id, score in filtered_ids}
    placeholders = ",".join("?" for _ in filtered_ids)
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT c.id, c.file_name, c.chunk_id, c.content
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.id IN ({placeholders}) AND d.status = 'indexed'
            """,
            [chunk_id for chunk_id, _ in filtered_ids],
        ).fetchall()

    by_id = {int(row["id"]): row for row in rows}
    sources: list[Source] = []
    for source_index, (chunk_id, score) in enumerate(filtered_ids, start=1):
        row = by_id.get(chunk_id)
        if row is None:
            continue
        sources.append(
            Source(
                id=source_index,
                file_name=row["file_name"],
                chunk_id=int(row["chunk_id"]),
                content=row["content"],
                score=scores[chunk_id],
            )
        )
    return sources


def append_history(user_id: int, question: str, answer: str, sources: list[Source]) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO chat_history (user_id, question, answer, sources_json)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, question, answer, json.dumps([source.model_dump() for source in sources], ensure_ascii=False)),
        )


def list_documents() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, file_name, size, file_type, status, chunks, uploaded_by, uploaded_at, error_message
            FROM documents
            ORDER BY uploaded_at DESC, id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_history(user_id: int, role: str) -> list[dict[str, Any]]:
    if role == "admin":
        query = """
            SELECT h.id, h.question, h.answer, h.sources_json, h.created_at, u.username
            FROM chat_history h
            JOIN users u ON u.id = h.user_id
            ORDER BY h.id DESC
            LIMIT 100
        """
        params: tuple[Any, ...] = ()
    else:
        query = """
            SELECT h.id, h.question, h.answer, h.sources_json, h.created_at, u.username
            FROM chat_history h
            JOIN users u ON u.id = h.user_id
            WHERE h.user_id = ?
            ORDER BY h.id DESC
            LIMIT 100
        """
        params = (user_id,)

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()

    history = []
    for row in rows:
        item = dict(row)
        item["sources"] = json.loads(item.pop("sources_json") or "[]")
        history.append(item)
    return history


def get_document(document_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    return dict(row) if row else None
