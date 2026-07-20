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

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        user: dict | None = None,
        knowledge_base_id: int | None = None,
    ) -> list[tuple[int, float]]:
        literal = "[" + ",".join(f"{item:.8g}" for item in query_vector) + "]"
        with get_db() as conn:
            if conn.postgres:
                clauses = ["c.embedding IS NOT NULL", "d.status = 'indexed'", "d.archived_at IS NULL"]
                params: list = [literal]
                if knowledge_base_id is not None:
                    clauses.append("d.knowledge_base_id = ?")
                    params.append(knowledge_base_id)
                role = str((user or {}).get("role", "reader"))
                if role != "system_admin":
                    user_id = int((user or {}).get("sub") or (user or {}).get("id") or 0)
                    department_id = (user or {}).get("department_id")
                    clearance_level = int((user or {}).get("clearance_level", 1))
                    permission_clauses = [
                        "d.security_level <= ?",
                        "(d.visible_roles = '[]'::jsonb OR d.visible_roles @> ?::jsonb)",
                        "(d.visible_users = '[]'::jsonb OR d.visible_users @> ?::jsonb)",
                    ]
                    permission_params = [clearance_level, json.dumps([role]), json.dumps([user_id])]
                    if department_id is None:
                        permission_clauses.append("d.department_scope = '[]'::jsonb")
                    else:
                        permission_clauses.append("(d.department_scope = '[]'::jsonb OR d.department_scope @> ?::jsonb)")
                        permission_params.append(json.dumps([int(department_id)]))
                    clauses.append("(d.security_level = 0 OR (" + " AND ".join(permission_clauses) + "))")
                    params.extend(permission_params)
                params.extend([literal, top_k])
                rows = conn.execute(
                    f"""
                    SELECT c.id, 1 - (c.embedding <=> ?::vector) AS score
                    FROM chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE {' AND '.join(clauses)}
                    ORDER BY c.embedding <=> ?::vector
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
                return [(int(row["id"]), float(row["score"])) for row in rows]
            rows = conn.execute("SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL").fetchall()
        def cosine(raw: str) -> float:
            vector = json.loads(raw); dot=sum(a*b for a,b in zip(query_vector,vector)); denom=math.sqrt(sum(a*a for a in query_vector))*math.sqrt(sum(b*b for b in vector)); return dot/denom if denom else 0.0
        return sorted(((int(row["id"]), cosine(row["embedding"])) for row in rows), key=lambda item:item[1], reverse=True)[:top_k]

    @property
    def count(self) -> int:
        with get_db() as conn: return int(conn.execute("SELECT COUNT(*) AS count FROM chunks WHERE embedding IS NOT NULL").fetchone()["count"])


vector_store = VectorStore()
