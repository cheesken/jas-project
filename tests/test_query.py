from unittest.mock import MagicMock, patch

import pytest

import services.query as query_module
from services.query import QueryService, Result


@pytest.fixture(autouse=True)
def reset_singleton():
    query_module._service = None
    yield
    query_module._service = None


def _raw(chunk_id, source_path, distance, content="text"):
    return {
        "id": chunk_id,
        "document": content,
        "metadata": {
            "source_path": source_path,
            "file_type": "pdf",
            "chunk_index": 0,
            "last_modified": "2026-04-21T14:00:00+00:00",
        },
        "distance": distance,
    }


def _patched_service(raw_results):
    service = QueryService.__new__(QueryService)
    service.k = 10
    service._embedder = MagicMock()
    service._embedder.embed.return_value = [0.0] * 384
    service._store = MagicMock()
    service._store.query.return_value = raw_results
    service._store.count.return_value = len(raw_results)
    return service


def test_search_returns_list_of_result_with_correct_shape():
    service = _patched_service([
        _raw("c1", "/Users/jane/Downloads/report.pdf", 0.1, "hello"),
    ])
    out = service.search("hello")
    assert len(out) == 1
    r = out[0]
    assert isinstance(r, Result)
    assert r.chunk_id == "c1"
    assert r.content == "hello"
    assert r.source_path == "/Users/jane/Downloads/report.pdf"
    assert r.file_name == "report.pdf"
    assert r.source_type == "Document"
    assert r.last_modified == "2026-04-21T14:00:00+00:00"


def test_results_sorted_by_score_descending():
    service = _patched_service([
        _raw("low", "/a.pdf", 0.9),
        _raw("high", "/b.pdf", 0.05),
        _raw("mid", "/c.pdf", 0.4),
    ])
    out = service.search("q")
    assert [r.chunk_id for r in out] == ["high", "mid", "low"]
    assert out[0].score >= out[1].score >= out[2].score


def test_file_name_is_basename_only():
    service = _patched_service([
        _raw("c1", "/Users/jane/very/deep/path/report.pdf", 0.1),
    ])
    assert service.search("q")[0].file_name == "report.pdf"


def test_score_clamped_above_zero_and_below_one():
    service = _patched_service([
        _raw("a", "/a.pdf", 1.5),   # distance > 1 → score should clamp to 0
        _raw("b", "/b.pdf", -0.2),  # distance < 0 → score should clamp to 1
        _raw("c", "/c.pdf", 0.3),   # normal case → score = 0.7
    ])
    out = service.search("q")
    by_id = {r.chunk_id: r for r in out}
    assert 0.0 <= by_id["a"].score <= 1.0
    assert 0.0 <= by_id["b"].score <= 1.0
    assert by_id["a"].score == 0.0
    assert by_id["b"].score == 1.0
    assert by_id["c"].score == pytest.approx(0.7)


def test_score_clamped_to_zero_when_distance_exactly_one():
    service = _patched_service([_raw("a", "/a.pdf", 1.0)])
    assert service.search("q")[0].score == 0.0


def test_empty_store_query_returns_empty_list():
    service = _patched_service([])
    assert service.search("q") == []


def test_empty_query_string_raises():
    service = _patched_service([])
    with pytest.raises(ValueError):
        service.search("")


def test_whitespace_query_string_raises():
    service = _patched_service([])
    with pytest.raises(ValueError):
        service.search("   ")


def test_module_level_singleton_only_constructs_once():
    counter = {"n": 0}
    real_init = QueryService.__init__

    def fake_init(self):
        counter["n"] += 1
        self.k = 10
        self._embedder = MagicMock()
        self._embedder.embed.return_value = [0.0] * 384
        self._store = MagicMock()
        self._store.query.return_value = []
        self._store.count.return_value = 0

    with patch.object(QueryService, "__init__", fake_init):
        query_module.search("hello")
        query_module.search("again")
        query_module.count()

    assert counter["n"] == 1
    QueryService.__init__ = real_init


def test_source_type_is_document_literal():
    service = _patched_service([
        _raw("c1", "/a.pdf", 0.1),
        _raw("c2", "/b.pdf", 0.2),
    ])
    out = service.search("q")
    assert all(r.source_type == "Document" for r in out)
