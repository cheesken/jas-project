from typing import List


class EmbeddingService:
    def __init__(self) -> None:
        raise NotImplementedError("EmbeddingService is owned by the embedding module — provide the implementation before invoking the worker")

    def embed(self, text: str) -> List[float]:
        raise NotImplementedError

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError
