from pathlib import Path
from typing import Any

from .config import UPLOAD_DIR, get_settings
from .document_loader import load_document
from .embeddings import embed_texts
from .llm import chat_completion
from .schemas import Source
from .splitter import split_text
from .vector_store import DOCUMENTS_PATH, HISTORY_PATH, read_json_list, vector_store, write_json_list


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


async def index_file(path: Path) -> int:
    settings = get_settings()
    text = load_document(path)
    chunks = split_text(text, settings.chunk_size, settings.chunk_overlap)
    vectors = await embed_texts(chunks)
    metadatas = [
        {
            "file_name": path.name,
            "chunk_id": i,
            "content": chunk,
        }
        for i, chunk in enumerate(chunks, start=1)
    ]
    vector_store.add(vectors, metadatas)
    _upsert_document(path.name, path.stat().st_size, len(chunks))
    return len(chunks)


async def rebuild_index() -> tuple[int, int]:
    vector_store.reset()
    documents: list[dict[str, Any]] = []
    total_chunks = 0

    for path in sorted(UPLOAD_DIR.iterdir()):
        if not path.is_file():
            continue
        text = load_document(path)
        chunks = split_text(text, get_settings().chunk_size, get_settings().chunk_overlap)
        vectors = await embed_texts(chunks)
        metadatas = [
            {"file_name": path.name, "chunk_id": i, "content": chunk}
            for i, chunk in enumerate(chunks, start=1)
        ]
        vector_store.add(vectors, metadatas)
        documents.append({"file_name": path.name, "size": path.stat().st_size, "chunks": len(chunks)})
        total_chunks += len(chunks)

    write_json_list(DOCUMENTS_PATH, documents)
    return len(documents), total_chunks


async def answer_question(question: str, top_k: int | None = None) -> tuple[str, list[Source]]:
    sources = await retrieve_sources(question, top_k)
    answer = await chat_completion(build_messages(question, sources))
    append_history(question, answer, sources)
    return answer, sources


async def retrieve_sources(question: str, top_k: int | None = None) -> list[Source]:
    settings = get_settings()
    query_vector = (await embed_texts([question]))[0]
    results = vector_store.search(query_vector, top_k or settings.top_k)
    return [
        Source(
            id=i,
            file_name=item["file_name"],
            chunk_id=item["chunk_id"],
            content=item["content"],
            score=item.get("score"),
        )
        for i, item in enumerate(results, start=1)
    ]


def append_history(question: str, answer: str, sources: list[Source]) -> None:
    history = read_json_list(HISTORY_PATH)
    history.append(
        {
            "question": question,
            "answer": answer,
            "sources": [source.model_dump() for source in sources],
        }
    )
    write_json_list(HISTORY_PATH, history[-100:])


def list_documents() -> list[dict[str, Any]]:
    return read_json_list(DOCUMENTS_PATH)


def list_history() -> list[dict[str, Any]]:
    return read_json_list(HISTORY_PATH)


def _upsert_document(file_name: str, size: int, chunks: int) -> None:
    documents = [doc for doc in read_json_list(DOCUMENTS_PATH) if doc["file_name"] != file_name]
    documents.append({"file_name": file_name, "size": size, "chunks": chunks})
    write_json_list(DOCUMENTS_PATH, sorted(documents, key=lambda item: item["file_name"]))
