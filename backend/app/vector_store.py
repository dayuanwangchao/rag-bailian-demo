"""pgvector persistence; no process-local FAISS index is used in production."""
import json
import math

from .database import get_db


class VectorStore:
    def add(self, vectors: list[list[float]], ids: list[int]) -> None:
        with get_db() as conn:
            for vector, chunk_id in zip(vectors, ids, strict=True):
                value = "[" + ",".join(f"{item:.8g}" for item in vector) + "]"
                conn.execute("UPDATE chunks SET embedding = ? WHERE id = ?", (value if conn.postgres else json.dumps(vector), chunk_id))

    def remove(self, ids: list[int]) -> None:
        # Chunk deletion is transactional; this only clears retained/archived rows.
        if not ids: return
        with get_db() as conn:
            conn.execute(f"UPDATE chunks SET embedding = NULL WHERE id IN ({','.join('?' for _ in ids)})", ids)

    def reset(self) -> None:
        with get_db() as conn: conn.execute("UPDATE chunks SET embedding = NULL")

    def search(self, query_vector: list[float], top_k: int) -> list[tuple[int, float]]:
        literal = "[" + ",".join(f"{item:.8g}" for item in query_vector) + "]"
        with get_db() as conn:
            if conn.postgres:
                rows = conn.execute("SELECT id, 1 - (embedding <=> ?::vector) AS score FROM chunks WHERE embedding IS NOT NULL ORDER BY embedding <=> ?::vector LIMIT ?", (literal, literal, top_k)).fetchall()
                return [(int(row["id"]), float(row["score"])) for row in rows]
            rows = conn.execute("SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL").fetchall()
        def cosine(raw: str) -> float:
            vector = json.loads(raw); dot=sum(a*b for a,b in zip(query_vector,vector)); denom=math.sqrt(sum(a*a for a in query_vector))*math.sqrt(sum(b*b for b in vector)); return dot/denom if denom else 0.0
        return sorted(((int(row["id"]), cosine(row["embedding"])) for row in rows), key=lambda item:item[1], reverse=True)[:top_k]

    @property
    def count(self) -> int:
        with get_db() as conn: return int(conn.execute("SELECT COUNT(*) AS count FROM chunks WHERE embedding IS NOT NULL").fetchone()["count"])


vector_store = VectorStore()
