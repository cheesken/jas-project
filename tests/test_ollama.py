import pytest
from unittest.mock import patch, MagicMock

from services.ollama import OllamaService, OllamaUnavailableError, OllamaTimeoutError
import requests


def make_mock_response(status_code: int, json_body=None, text: str = ""):
    mock = MagicMock()
    mock.status_code = status_code
    mock.text = text
    if json_body is not None:
        mock.json.return_value = json_body
    else:
        mock.json.side_effect = ValueError("No JSON")
    return mock


class TestOllamaServiceGenerate:
    def test_happy_path(self):
        with patch("services.ollama.requests.post") as mock_post:
            mock_post.return_value = make_mock_response(200, {"response": "Hello!"})
            service = OllamaService()
            result = service.generate("hi", ["context"])
        assert result == "Hello!"

    def test_connection_error_raises_unavailable(self):
        with patch("services.ollama.requests.post") as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError("refused")
            service = OllamaService()
            with pytest.raises(OllamaUnavailableError) as exc_info:
                service.generate("hi", ["ctx"])
        assert "Ollama" in str(exc_info.value)
        assert "running" in str(exc_info.value)

    def test_timeout_raises_timeout_error(self):
        with patch("services.ollama.requests.post") as mock_post:
            mock_post.side_effect = requests.exceptions.Timeout()
            service = OllamaService()
            with pytest.raises(OllamaTimeoutError):
                service.generate("hi", ["ctx"])

    def test_non_200_status_raises_unavailable(self):
        with patch("services.ollama.requests.post") as mock_post:
            mock_post.return_value = make_mock_response(500, text="Internal Server Error")
            service = OllamaService()
            with pytest.raises(OllamaUnavailableError) as exc_info:
                service.generate("hi", ["ctx"])
        assert "500" in str(exc_info.value)

    def test_malformed_json_raises_unavailable(self):
        with patch("services.ollama.requests.post") as mock_post:
            mock_post.return_value = make_mock_response(200, json_body=None, text="not-json")
            service = OllamaService()
            with pytest.raises(OllamaUnavailableError):
                service.generate("hi", ["ctx"])

    def test_missing_response_key_raises_unavailable(self):
        with patch("services.ollama.requests.post") as mock_post:
            mock_post.return_value = make_mock_response(200, {"foo": "bar"})
            service = OllamaService()
            with pytest.raises(OllamaUnavailableError):
                service.generate("hi", ["ctx"])


class TestOllamaServicePrompt:
    def test_prompt_contains_query_and_chunks(self):
        service = OllamaService()
        prompt = service._build_prompt("Q?", ["chunk1", "chunk2"])
        assert "Q?" in prompt
        assert "chunk1" in prompt
        assert "chunk2" in prompt
        assert "Question:" in prompt
        assert "Answer:" in prompt

    def test_empty_context_uses_placeholder(self):
        service = OllamaService()
        prompt = service._build_prompt("Q?", [])
        assert "(no context)" in prompt

    def test_model_is_pinned(self):
        assert OllamaService().model == "llama3:8b"
