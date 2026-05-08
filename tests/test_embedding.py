import sys

# Remove conftest stubs so real sentence_transformers is used
for _mod in list(sys.modules):
    if _mod in ("sentence_transformers",) or _mod.startswith(
        ("sentence_transformers.", "services.embedding")
    ):
        del sys.modules[_mod]

import pytest
import numpy as np


@pytest.fixture(scope="module")
def embedder():
    from services.embedding import EmbeddingService
    return EmbeddingService()


# Test 1: embed returns 384 floats
def test_embed_returns_384_floats(embedder):
    result = embedder.embed("hello world")
    assert isinstance(result, list)
    assert len(result) == 384
    assert all(isinstance(x, float) for x in result)


# Test 2: embed_batch returns correct shape
def test_embed_batch_shape(embedder):
    result = embedder.embed_batch(["a", "b", "c"])
    assert isinstance(result, list)
    assert len(result) == 3
    for vec in result:
        assert isinstance(vec, list)
        assert len(vec) == 384


# Test 3: embed is deterministic
def test_embed_deterministic(embedder):
    v1 = embedder.embed("hello")
    v2 = embedder.embed("hello")
    assert v1 == v2


# Test 4: different texts produce different vectors
def test_embed_different_texts(embedder):
    v1 = np.array(embedder.embed("hello"))
    v2 = np.array(embedder.embed("car"))
    cosine_sim = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
    assert cosine_sim < 0.95


# Test 5: embed empty string raises ValueError
def test_embed_empty_string(embedder):
    with pytest.raises(ValueError):
        embedder.embed("")


# Test 6: embed whitespace raises ValueError
def test_embed_whitespace(embedder):
    with pytest.raises(ValueError):
        embedder.embed("   ")


# Test 7: embed_batch empty list returns empty list
def test_embed_batch_empty(embedder):
    result = embedder.embed_batch([])
    assert result == []


# Test 8: embed_batch with empty string raises ValueError
def test_embed_batch_with_empty(embedder):
    with pytest.raises(ValueError):
        embedder.embed_batch(["valid", ""])
