import json
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from .config import INDEX_DIR


INDEX_PATH = INDEX_DIR / "index.faiss"
METADATA_PATH = INDEX_DIR / "metadata.json"
DOCUMENTS_PATH = INDEX_DIR / "documents.json"
HISTORY_PATH = INDEX_DIR / "history.json"


class VectorStore:
    def __init__(self) -> None:
        self.index: faiss.Index | None = None
        self.metadata: list[dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        if INDEX_PATH.exists() and METADATA_PATH.exists():
            self.index = faiss.read_index(str(INDEX_PATH))
            self.metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        else:
            self.index = None
            self.metadata = []

    def save(self) -> None:
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        if self.index is not None:
            faiss.write_index(self.index, str(INDEX_PATH))
        METADATA_PATH.write_text(
            json.dumps(self.metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def reset(self) -> None:
        self.index = None
        self.metadata = []
        for path in (INDEX_PATH, METADATA_PATH):
            if path.exists():
                path.unlink()

    def add(self, vectors: list[list[float]], metadatas: list[dict[str, Any]]) -> None:
        if not vectors:
            return
        array = np.array(vectors, dtype="float32")
        faiss.normalize_L2(array)

        if self.index is None:
            self.index = faiss.IndexFlatIP(array.shape[1])
        if self.index.d != array.shape[1]:
            raise ValueError("Embedding dimension changed. Please rebuild the index.")

        self.index.add(array)
        self.metadata.extend(metadatas)
        self.save()

    def search(self, query_vector: list[float], top_k: int) -> list[dict[str, Any]]:
        if self.index is None or self.index.ntotal == 0:
            return []

        query = np.array([query_vector], dtype="float32")
        faiss.normalize_L2(query)
        scores, indices = self.index.search(query, min(top_k, self.index.ntotal))

        results: list[dict[str, Any]] = []
        for score, index in zip(scores[0], indices[0], strict=False):
            if index < 0:
                continue
            item = dict(self.metadata[int(index)])
            item["score"] = float(score)
            item["id"] = int(index) + 1
            results.append(item)
        return results

    @property
    def count(self) -> int:
        return int(self.index.ntotal) if self.index is not None else 0


def read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_list(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


vector_store = VectorStore()
