import threading

import faiss
import numpy as np

from .config import INDEX_DIR


INDEX_PATH = INDEX_DIR / "index.faiss"


class VectorStore:
    def __init__(self) -> None:
        self.index: faiss.IndexIDMap2 | None = None
        self.lock = threading.Lock()
        self.load()

    def load(self) -> None:
        if INDEX_PATH.exists():
            self.index = faiss.read_index(str(INDEX_PATH))
            if not isinstance(self.index, faiss.IndexIDMap2):
                self.index = None
                INDEX_PATH.unlink()
        else:
            self.index = None

    def save(self) -> None:
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        if self.index is not None:
            faiss.write_index(self.index, str(INDEX_PATH))

    def reset(self) -> None:
        with self.lock:
            self.index = None
            if INDEX_PATH.exists():
                INDEX_PATH.unlink()

    def add(self, vectors: list[list[float]], ids: list[int]) -> None:
        if not vectors:
            return
        if len(vectors) != len(ids):
            raise ValueError("vectors and ids length mismatch")

        array = np.array(vectors, dtype="float32")
        faiss.normalize_L2(array)
        id_array = np.array(ids, dtype="int64")

        with self.lock:
            if self.index is None:
                self.index = faiss.IndexIDMap2(faiss.IndexFlatIP(array.shape[1]))
            if self.index.d != array.shape[1]:
                raise ValueError("Embedding dimension changed. Please rebuild the index.")

            self.index.add_with_ids(array, id_array)
            self.save()

    def remove(self, ids: list[int]) -> None:
        if self.index is None or not ids:
            return
        with self.lock:
            id_array = np.array(ids, dtype="int64")
            self.index.remove_ids(id_array)
            self.save()

    def search(self, query_vector: list[float], top_k: int) -> list[tuple[int, float]]:
        if self.index is None or self.index.ntotal == 0:
            return []

        query = np.array([query_vector], dtype="float32")
        faiss.normalize_L2(query)
        scores, indices = self.index.search(query, min(top_k, self.index.ntotal))

        results: list[tuple[int, float]] = []
        for score, index in zip(scores[0], indices[0], strict=False):
            if index < 0:
                continue
            results.append((int(index), float(score)))
        return results

    @property
    def count(self) -> int:
        return int(self.index.ntotal) if self.index is not None else 0


vector_store = VectorStore()
