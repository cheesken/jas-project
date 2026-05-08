"""
Test-level conftest. Heavy dependency stubs are applied in the root conftest.py
which is loaded before this file.

Stubs api.ingest so api.main can be imported in unit tests without pulling
in celery/chromadb through worker.tasks.
"""
import sys
import types
from fastapi import APIRouter

if "api.ingest" not in sys.modules:
    _ingest = types.ModuleType("api.ingest")
    _ingest.router = APIRouter()
    sys.modules["api.ingest"] = _ingest
