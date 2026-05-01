import os
from dataclasses import dataclass
from typing import List, Optional

from services.embedding import EmbeddingService
from services.vector_store import VectorStore


@dataclass
class Result:
    chunk_id: str
    content: str
    source_path: str
    file_name: str
    source_type: str
    score: float
    last_modified: str


class QueryService:
    def __init__(self) -> None:
        self.k = 10
        self._embedder = EmbeddingService()
        self._store = VectorStore()

    def search(self, query: str, k: Optional[int] = None) -> List[Result]:
        if query.strip() == "":
            raise ValueError("Query must not be empty")
        effective_k = k if k is not None else self.k

        query_vector = self._embedder.embed(query)
        raw = self._store.query(query_vector, k=effective_k)

        results = [
            Result(
                chunk_id=r["id"],
                content=r["document"],
                source_path=r["metadata"]["source_path"],
                file_name=os.path.basename(r["metadata"]["source_path"]),
                source_type="Document",
                score=max(0.0, min(1.0, 1.0 - r["distance"])),
                last_modified=r["metadata"]["last_modified"],
            )
            for r in raw
        ]
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def count(self) -> int:
        return self._store.count()


_service: Optional[QueryService] = None


def _get_service() -> QueryService:
    global _service
    if _service is None:
        _service = QueryService()
    return _service


def search(query: str, k: int = 10) -> List[Result]:
    return _get_service().search(query, k=k)


def count() -> int:
    return _get_service().count()
