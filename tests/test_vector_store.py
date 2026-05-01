import numpy as np
import pytest

from parsers.base import Chunk
from services.vector_store import VectorStore


def _vec(seed: int = 0) -> list:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(384).astype("float32").tolist()


def _chunk(idx: int) -> Chunk:
    return Chunk(
        id=f"chunk-{idx}",
        content=f"content of chunk {idx}",
        token_count=42,
        chunk_index=idx,
        start_char=0,
        end_char=10,
        page_number=1,
    )


def _meta(path: str = "/tmp/doc.pdf", idx: int = 0) -> dict:
    return {
        "source_path": path,
        "file_type": "pdf",
        "chunk_index": idx,
        "last_modified": "2026-05-01T00:00:00+00:00",
    }


@pytest.fixture
def store(tmp_path):
    return VectorStore(persist_path=str(tmp_path / "chroma"))


def test_add_then_query_returns_added_chunk_first(store):
    v = _vec(1)
    store.add([_chunk(0)], [v], [_meta(idx=0)])
    results = store.query(v, k=1)
    assert len(results) == 1
    assert results[0]["id"] == "chunk-0"


def test_query_returns_k_results_sorted(store):
    chunks = [_chunk(i) for i in range(5)]
    vectors = [_vec(i + 1) for i in range(5)]
    metas = [_meta(idx=i) for i in range(5)]
    store.add(chunks, vectors, metas)
    results = store.query(_vec(2), k=3)
    assert len(results) == 3
    distances = [r["distance"] for r in results]
    assert distances == sorted(distances)


def test_query_more_than_available_returns_all(store):
    chunks = [_chunk(i) for i in range(5)]
    vectors = [_vec(i + 1) for i in range(5)]
    metas = [_meta(idx=i) for i in range(5)]
    store.add(chunks, vectors, metas)
    assert len(store.query(_vec(7), k=10)) == 5


def test_query_empty_collection_returns_empty(store):
    assert store.query(_vec(0), k=5) == []


def test_delete_by_source_path(store):
    keep_meta = _meta(path="/tmp/keep.pdf", idx=0)
    drop_meta_a = _meta(path="/tmp/drop.pdf", idx=0)
    drop_meta_b = _meta(path="/tmp/drop.pdf", idx=1)

    store.add(
        [_chunk(0), _chunk(1), _chunk(2)],
        [_vec(1), _vec(2), _vec(3)],
        [keep_meta, drop_meta_a, drop_meta_b],
    )
    assert store.count() == 3
    store.delete("/tmp/drop.pdf")
    assert store.count() == 1
    remaining = store.query(_vec(1), k=10)
    assert all(r["metadata"]["source_path"] == "/tmp/keep.pdf" for r in remaining)


def test_add_length_mismatch_raises(store):
    with pytest.raises(ValueError):
        store.add([_chunk(0), _chunk(1)], [_vec(1)], [_meta(idx=0)])


def test_add_wrong_dimension_raises(store):
    bad = [0.0] * 100
    with pytest.raises(ValueError):
        store.add([_chunk(0)], [bad], [_meta(idx=0)])


def test_add_missing_metadata_key_raises(store):
    bad_meta = {"file_type": "pdf", "chunk_index": 0, "last_modified": "2026-05-01T00:00:00+00:00"}
    with pytest.raises(ValueError):
        store.add([_chunk(0)], [_vec(1)], [bad_meta])


def test_count_reflects_additions_and_deletions(store):
    assert store.count() == 0
    store.add([_chunk(0)], [_vec(1)], [_meta(path="/tmp/a.pdf", idx=0)])
    store.add([_chunk(1)], [_vec(2)], [_meta(path="/tmp/b.pdf", idx=0)])
    assert store.count() == 2
    store.delete("/tmp/a.pdf")
    assert store.count() == 1


def test_cosine_distance_of_identical_vector_is_zero(store):
    v = _vec(42)
    store.add([_chunk(0)], [v], [_meta(idx=0)])
    results = store.query(v, k=1)
    assert results[0]["distance"] == pytest.approx(0, abs=1e-5)
