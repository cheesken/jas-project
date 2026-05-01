"""
Stub out heavy runtime dependencies so unit tests can import backend modules
without needing chromadb, sentence-transformers, celery, redis, or pdfplumber
installed locally. Stubs are placed in sys.modules before any test module is
collected, so all imports in the modules under test resolve cleanly.

api.ingest is Ananya's module (not yet written); stub it so api.main can be
imported in tests that exercise the query endpoint.
"""
import sys
from unittest.mock import MagicMock
from fastapi import APIRouter


def _stub(name: str) -> MagicMock:
    mock = MagicMock()
    sys.modules[name] = mock
    return mock


for _pkg in (
    "chromadb",
    "chromadb.errors",
    "sentence_transformers",
    "celery",
    "celery.exceptions",
    "redis",
    "redis.exceptions",
    "pdfplumber",
    "tiktoken",
):
    if _pkg not in sys.modules:
        _stub(_pkg)

# Stub Ananya's ingest router so api.main can be imported without it existing.
if "api.ingest" not in sys.modules:
    _ingest_stub = MagicMock()
    _ingest_stub.router = APIRouter()
    sys.modules["api.ingest"] = _ingest_stub
