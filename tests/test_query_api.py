import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Pre-import so patch("api.query.*") can resolve the module by name.
import api.query  # noqa: F401
import api.main   # noqa: F401


def make_result(n: int) -> MagicMock:
    r = MagicMock()
    r.chunk_id = f"chunk-{n}"
    r.content = f"content {n}"
    r.source_path = f"/data/file{n}.pdf"
    r.file_name = f"file{n}.pdf"
    r.source_type = "Document"
    r.score = round(0.9 - n * 0.1, 1)
    r.last_modified = "2026-04-21T14:00:00+00:00"
    return r


@pytest.fixture
def client():
    # Import app inside the fixture so patches applied in individual tests
    # take effect before the module-level singleton is accessed.
    with patch("api.query.count", return_value=5), \
         patch("api.query.search", return_value=[make_result(0)]), \
         patch("api.query.OllamaService"):
        from api.main import app
        return TestClient(app, raise_server_exceptions=False)


class TestQueryEndpoint:
    def test_valid_query_populated_db_ollama_works(self):
        results = [make_result(i) for i in range(3)]
        with patch("api.query.count", return_value=5), \
             patch("api.query.search", return_value=results) as mock_search, \
             patch("api.query.OllamaService") as mock_ollama_cls:
            mock_ollama_cls.return_value.generate.return_value = "answer"
            from api.main import app
            c = TestClient(app, raise_server_exceptions=False)
            r = c.get("/query", params={"q": "test query"})

        assert r.status_code == 200
        body = r.json()
        assert len(body["results"]) == 3
        assert body["response"] == "answer"
        for result in body["results"]:
            for key in ("chunk_id", "content", "file_name", "source_type", "score", "last_modified"):
                assert key in result

    def test_empty_q_returns_422(self):
        from api.main import app
        c = TestClient(app, raise_server_exceptions=False)
        r = c.get("/query", params={"q": ""})
        assert r.status_code == 422

    def test_whitespace_only_q_returns_422(self):
        with patch("api.query.count", return_value=5), \
             patch("api.query.search", side_effect=ValueError("Query must not be empty")):
            from api.main import app
            c = TestClient(app, raise_server_exceptions=False)
            r = c.get("/query", params={"q": "  "})
        assert r.status_code == 422
        assert "Query must not be empty" in r.json()["detail"]

    def test_top_k_out_of_range_returns_422(self):
        from api.main import app
        c = TestClient(app, raise_server_exceptions=False)
        assert c.get("/query", params={"q": "hi", "top_k": 100}).status_code == 422
        assert c.get("/query", params={"q": "hi", "top_k": 0}).status_code == 422

    def test_empty_db_returns_200_with_no_documents_message(self):
        with patch("api.query.count", return_value=0) as mock_count, \
             patch("api.query.search") as mock_search:
            from api.main import app
            c = TestClient(app, raise_server_exceptions=False)
            r = c.get("/query", params={"q": "hello"})

        assert r.status_code == 200
        body = r.json()
        assert body["results"] == []
        assert body["response"].startswith("No documents")
        mock_search.assert_not_called()

    def test_populated_db_no_matches(self):
        with patch("api.query.count", return_value=5), \
             patch("api.query.search", return_value=[]), \
             patch("api.query.OllamaService") as mock_ollama_cls:
            from api.main import app
            c = TestClient(app, raise_server_exceptions=False)
            r = c.get("/query", params={"q": "xyzzy"})

        assert r.status_code == 200
        body = r.json()
        assert body["results"] == []
        assert body["response"].startswith("No matches")
        mock_ollama_cls.return_value.generate.assert_not_called()

    def test_ollama_unavailable_fallback(self):
        from services.ollama import OllamaUnavailableError
        with patch("api.query.count", return_value=5), \
             patch("api.query.search", return_value=[make_result(0)]), \
             patch("api.query.OllamaService") as mock_ollama_cls:
            mock_ollama_cls.return_value.generate.side_effect = OllamaUnavailableError("down")
            from api.main import app
            c = TestClient(app, raise_server_exceptions=False)
            r = c.get("/query", params={"q": "question"})

        assert r.status_code == 200
        body = r.json()
        assert len(body["results"]) == 1
        assert body["response"] == "LLM unavailable. Showing raw search results only."

    def test_ollama_timeout_fallback(self):
        from services.ollama import OllamaTimeoutError
        with patch("api.query.count", return_value=5), \
             patch("api.query.search", return_value=[make_result(0)]), \
             patch("api.query.OllamaService") as mock_ollama_cls:
            mock_ollama_cls.return_value.generate.side_effect = OllamaTimeoutError("timeout")
            from api.main import app
            c = TestClient(app, raise_server_exceptions=False)
            r = c.get("/query", params={"q": "question"})

        assert r.status_code == 200
        assert r.json()["response"] == "LLM unavailable. Showing raw search results only."

    def test_top_k_passed_to_search(self):
        with patch("api.query.count", return_value=5), \
             patch("api.query.search", return_value=[make_result(0)]) as mock_search, \
             patch("api.query.OllamaService") as mock_ollama_cls:
            mock_ollama_cls.return_value.generate.return_value = "ok"
            from api.main import app
            c = TestClient(app, raise_server_exceptions=False)
            c.get("/query", params={"q": "test", "top_k": 5})

        mock_search.assert_called_once_with(query="test", k=5)

    def test_source_path_not_in_response(self):
        with patch("api.query.count", return_value=5), \
             patch("api.query.search", return_value=[make_result(0)]), \
             patch("api.query.OllamaService") as mock_ollama_cls:
            mock_ollama_cls.return_value.generate.return_value = "ok"
            from api.main import app
            c = TestClient(app, raise_server_exceptions=False)
            r = c.get("/query", params={"q": "test"})

        for result in r.json()["results"]:
            assert "source_path" not in result
