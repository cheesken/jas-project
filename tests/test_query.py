import os
from unittest.mock import MagicMock, patch

import pytest

import services.query as query_module
from services.graph import KnowledgeGraph
from services.query import DIRECT_BOOST, NEIGHBOR_BOOST, QueryService, Result

KG_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "kg_sample.json")
WHATSAPP = "/Users/test/notes/whatsapp_export.txt"
MEETING = "/Users/test/notes/meeting_notes_q1.txt"
TRIP = "/Users/test/docs/trip.pdf"


@pytest.fixture(autouse=True)
def reset_singleton():
    query_module._service = None
    yield
    query_module._service = None


def _raw(chunk_id, source_path, distance, content="text", file_type="pdf"):
    return {
        "id": chunk_id,
        "document": content,
        "metadata": {
            "source_path": source_path,
            "file_type": file_type,
            "chunk_index": 0,
            "last_modified": "2026-04-21T14:00:00+00:00",
        },
        "distance": distance,
    }


def _sample_kg():
    kg = KnowledgeGraph(graph_path=KG_FIXTURE)
    kg.load()
    return kg


def _patched_service(raw_results, kg=None, kg_results=None):
    service = QueryService.__new__(QueryService)
    service.k = 10
    service._embedder = MagicMock()
    service._embedder.embed.return_value = [0.0] * 384
    service._store = MagicMock()

    def fake_query(vector, k, where=None):
        if where is None:
            return raw_results
        allowed = set(where["source_path"]["$in"])
        return [r for r in (kg_results or []) if r["metadata"]["source_path"] in allowed]

    service._store.query.side_effect = fake_query
    service._store.count.return_value = len(raw_results)
    graph = kg or KnowledgeGraph(graph_path="/nonexistent/kg.json")
    service._graph = lambda: graph
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


def test_image_results_have_image_source_type():
    service = _patched_service([
        _raw("c1", "/a.pdf", 0.1),
        _raw("c2", "/shot.png", 0.2, file_type="image"),
    ])
    out = {r.chunk_id: r.source_type for r in service.search("q")}
    assert out == {"c1": "Document", "c2": "Image"}


def test_source_type_labels_for_every_ingestable_type():
    service = _patched_service([
        _raw("c1", "/a.pdf", 0.1, file_type="pdf"),
        _raw("c2", "/notes.txt", 0.2, file_type="txt"),
        _raw("c3", "/shot.png", 0.3, file_type="image"),
        _raw("c4", "/Chrome/Default/History", 0.4, file_type="browser_history"),
    ])
    out = {r.chunk_id: r.source_type for r in service.search("q")}
    assert out == {"c1": "Document", "c2": "Document", "c3": "Image", "c4": "Browser History"}


def test_browser_history_result_uses_page_title_and_visit_time():
    raw = _raw("c1", "/Chrome/Default/History", 0.1, "Noosh Noshery · https://yelp.com/biz/noosh",
               file_type="browser_history")
    raw["metadata"].update(title="Noosh Noshery", url="https://yelp.com/biz/noosh",
                           last_modified="2026-03-15T19:00:00+00:00")
    (r,) = _patched_service([raw]).search("q")
    assert r.file_name == "Noosh Noshery"
    assert r.source_type == "Browser History"
    assert r.last_modified == "2026-03-15T19:00:00+00:00"
    assert r.source_path == "/Chrome/Default/History"


def test_no_entities_in_query_leaves_scores_untouched():
    service = _patched_service([_raw("c1", WHATSAPP, 0.4)], kg=_sample_kg())
    out = service.search("something unrelated")
    assert out[0].score == pytest.approx(0.6)
    assert out[0].entities == []
    assert service._store.query.call_count == 1


def test_direct_entity_mention_gets_direct_boost():
    service = _patched_service(
        [_raw("w", WHATSAPP, 0.5), _raw("t", TRIP, 0.4)],
        kg=_sample_kg(),
    )
    by_id = {r.chunk_id: r for r in service.search("what did Tara recommend")}
    assert by_id["w"].score == pytest.approx(0.5 + DIRECT_BOOST)
    assert "Tara" in by_id["w"].entities
    assert by_id["t"].score == pytest.approx(0.6)
    assert by_id["t"].entities == []


def test_boost_reorders_results():
    service = _patched_service(
        [_raw("t", TRIP, 0.4), _raw("w", WHATSAPP, 0.5)],
        kg=_sample_kg(),
    )
    assert [r.chunk_id for r in service.search("Tara")] == ["w", "t"]


def test_neighbor_docs_get_weighted_neighbor_boost():
    service = _patched_service(
        [_raw("w", WHATSAPP, 0.5), _raw("m", MEETING, 0.5)],
        kg=_sample_kg(),
    )
    by_id = {r.chunk_id: r for r in service.search("noosh noshery")}
    assert by_id["w"].score == pytest.approx(0.5 + DIRECT_BOOST)
    assert by_id["m"].score == pytest.approx(0.5 + NEIGHBOR_BOOST)
    assert set(by_id["m"].entities) == {"Tara", "Mountain View"}


def test_kg_only_documents_are_fetched_and_merged():
    service = _patched_service(
        [_raw("t", TRIP, 0.3)],
        kg=_sample_kg(),
        kg_results=[_raw("m1", MEETING, 0.7), _raw("m2", MEETING, 0.6), _raw("w1", WHATSAPP, 0.65)],
    )
    out = service.search("castro st")
    ids = [r.chunk_id for r in out]
    assert "m2" in ids and "m1" not in ids
    assert "w1" in ids
    where = service._store.query.call_args_list[1].kwargs["where"]
    assert set(where["source_path"]["$in"]) == {MEETING, WHATSAPP}
    by_id = {r.chunk_id: r for r in out}
    assert by_id["m2"].score == pytest.approx(0.4 + DIRECT_BOOST)


def test_merge_does_not_duplicate_chunks():
    merged = QueryService.merge_kg_results(
        [_raw("a", "/a.pdf", 0.1)],
        [_raw("a", "/a.pdf", 0.1), _raw("b", "/b.pdf", 0.2)],
    )
    assert [r["id"] for r in merged] == ["a", "b"]


def test_results_truncated_to_k_after_merge():
    service = _patched_service(
        [_raw("t", TRIP, 0.3)],
        kg=_sample_kg(),
        kg_results=[_raw("m", MEETING, 0.6), _raw("w", WHATSAPP, 0.65)],
    )
    out = service.search("castro st", k=1)
    assert len(out) == 1


def test_boosted_score_capped_at_one():
    service = _patched_service([_raw("w", WHATSAPP, 0.0)], kg=_sample_kg())
    assert service.search("Tara")[0].score == 1.0


def test_graph_failure_falls_back_to_vector_results():
    service = _patched_service([_raw("w", WHATSAPP, 0.5)])

    def broken():
        raise RuntimeError("kg unavailable")

    service._graph = broken
    out = service.search("Tara")
    assert out[0].score == pytest.approx(0.5)
    assert out[0].entities == []


def test_kg_chunk_lookup_failure_keeps_vector_results():
    service = _patched_service([_raw("t", TRIP, 0.3)], kg=_sample_kg())
    raw = service._store.query.side_effect

    def flaky(vector, k, where=None):
        if where is not None:
            raise RuntimeError("chroma down")
        return raw(vector, k)

    service._store.query.side_effect = flaky
    assert [r.chunk_id for r in service.search("castro st")] == ["t"]
