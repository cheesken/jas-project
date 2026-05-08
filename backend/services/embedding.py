import os
from typing import List

from sentence_transformers import SentenceTransformer


class EmbeddingService:
    def __init__(self) -> None:
        model_name = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        self.model_name = model_name
        self.batch_size = 64
        self._device = "cpu"
        self._model = SentenceTransformer(model_name, device=self._device)

    def embed(self, text: str) -> List[float]:
        if text == "" or text.strip() == "":
            raise ValueError("Cannot embed empty text")
        return self._model.encode(text, convert_to_numpy=True).tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        for t in texts:
            if t == "" or t.strip() == "":
                raise ValueError("Cannot embed empty text")
        return self._model.encode(texts, batch_size=self.batch_size, convert_to_numpy=True).tolist()
