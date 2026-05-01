import os
from typing import List, Optional

import chromadb

from parsers.base import Chunk


REQUIRED_METADATA_KEYS = {"source_path", "file_type", "chunk_index", "last_modified"}


class VectorStore:
    def __init__(self, persist_path: Optional[str] = None) -> None:
        self._persist_path = persist_path or os.environ["CHROMA_PATH"]
        self.collection_name = "chunks"
        self.dimension = 384
        self._client = chromadb.PersistentClient(path=self._persist_path)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(
        self,
        chunks: List[Chunk],
        vectors: List[List[float]],
        metadatas: List[dict],
    ) -> None:
        if not (len(chunks) == len(vectors) == len(metadatas)):
            raise ValueError(
                f"Length mismatch: chunks={len(chunks)}, vectors={len(vectors)}, metadatas={len(metadatas)}"
            )
        for i, vec in enumerate(vectors):
            if len(vec) != self.dimension:
                raise ValueError(
                    f"Vector at index {i} has dimension {len(vec)}, expected {self.dimension}"
                )
        for i, meta in enumerate(metadatas):
            missing = REQUIRED_METADATA_KEYS - set(meta.keys())
            if missing:
                raise ValueError(
                    f"Metadata at index {i} is missing required keys: {sorted(missing)}"
                )

        self._collection.add(
            ids=[c.id for c in chunks],
            embeddings=vectors,
            documents=[c.content for c in chunks],
            metadatas=metadatas,
        )

    def query(self, vector: List[float], k: int) -> List[dict]:
        raw = self._collection.query(query_embeddings=[vector], n_results=k)

        ids_batch = raw.get("ids") or []
        if not ids_batch or not ids_batch[0]:
            return []

        ids = ids_batch[0]
        docs = (raw.get("documents") or [[]])[0]
        metas = (raw.get("metadatas") or [[]])[0]
        dists = (raw.get("distances") or [[]])[0]

        results = [
            {"id": ids[i], "document": docs[i], "metadata": metas[i], "distance": dists[i]}
            for i in range(len(ids))
        ]
        results.sort(key=lambda r: r["distance"])
        return results

    def delete(self, source_path: str) -> None:
        self._collection.delete(where={"source_path": source_path})

    def count(self) -> int:
        return self._collection.count()
