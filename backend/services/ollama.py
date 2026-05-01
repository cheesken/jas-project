import os
import logging
import requests
from typing import List

logger = logging.getLogger(__name__)


class OllamaUnavailableError(Exception):
    """Raised when Ollama cannot be reached."""


class OllamaTimeoutError(Exception):
    """Raised when Ollama takes longer than the timeout to respond."""


class OllamaService:
    PROMPT_TEMPLATE = (
        "You are a helpful personal memory assistant. Answer the question "
        "based only on the provided context. If the answer is not in the "
        "context, say \"I could not find that in your documents.\"\n\n"
        "Context:\n{context}\n\n"
        "Question: {query}\n"
        "Answer:"
    )

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = base_url or os.environ.get("OLLAMA_URL", "http://localhost:11434")
        # PINNED — not "llama3", which can alias to a different version across Ollama releases
        self.model = model or "llama3:8b"
        self.timeout_seconds = 120

    def _build_prompt(self, query: str, context_chunks: List[str]) -> str:
        context = "\n\n".join(context_chunks) if context_chunks else "(no context)"
        return self.PROMPT_TEMPLATE.format(context=context, query=query)

    def generate(self, query: str, context_chunks: List[str]) -> str:
        prompt = self._build_prompt(query, context_chunks)
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=self.timeout_seconds,
            )
        except requests.exceptions.Timeout as e:
            raise OllamaTimeoutError(
                f"Ollama did not respond within {self.timeout_seconds}s"
            ) from e
        except requests.exceptions.ConnectionError as e:
            raise OllamaUnavailableError(
                "Could not reach Ollama. Is it running? "
                "Start it with: `ollama serve` and pull the model with `ollama pull llama3:8b`."
            ) from e

        if response.status_code != 200:
            raise OllamaUnavailableError(
                f"Ollama returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            return response.json()["response"]
        except (ValueError, KeyError) as e:
            raise OllamaUnavailableError(f"Ollama returned malformed response: {e}") from e
