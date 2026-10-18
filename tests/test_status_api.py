from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.status import router
from services.db import SQLiteDB


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_job(job_id, file_hash, status, completed_at=None, file_type="pdf", path=None):
    return {
        "job_id": job_id,
        "file_path": path or f"/tmp/{job_id}.pdf",
        "file_name": f"{job_id}.pdf",
        "file_type": file_type,
        "file_size": 1024,
        "file_hash": file_hash,
        "status": status,
        "error_message": None,
        "chunk_count": 0,
        "retry_count": 0,
        "created_at": _now(),
        "updated_at": _now(),
        "completed_at": completed_at,
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "status.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    SQLiteDB(db_path=db_path)  # ensure schema exists
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), db_path


def test_empty_db_returns_zeroed_summary(client):
    tc, _ = client
    r = tc.get("/status")
    assert r.status_code == 200
    assert r.json() == {
        "total_docs": 0, "last_updated": None, "pending_jobs": 0,
        "total_files": 0, "failed_docs": 0, "percent_indexed": None, "by_type": {},
    }


def test_two_completed_one_pending(client):
    tc, db_path = client
    db = SQLiteDB(db_path=db_path)
    db.insert_job(_make_job("c1", "hc1", "COMPLETED", completed_at="2026-04-01T10:00:00+00:00"))
    db.insert_job(_make_job("c2", "hc2", "COMPLETED", completed_at="2026-04-15T10:00:00+00:00"))
    db.insert_job(_make_job("p1", "hp1", "PENDING"))

    body = tc.get("/status").json()
    assert body["total_docs"] == 2
    assert body["pending_jobs"] == 1
    assert body["last_updated"] == "2026-04-15T10:00:00+00:00"


def test_all_in_flight_statuses_count_toward_pending(client):
    tc, db_path = client
    db = SQLiteDB(db_path=db_path)
    for i, status in enumerate(["PENDING", "PROCESSING", "CHUNKING", "EMBEDDING"]):
        db.insert_job(_make_job(f"j{i}", f"h{i}", status))

    body = tc.get("/status").json()
    assert body["pending_jobs"] == 4
    assert body["total_docs"] == 0


def test_failed_jobs_excluded_from_totals(client):
    tc, db_path = client
    db = SQLiteDB(db_path=db_path)
    db.insert_job(_make_job("c1", "hc1", "COMPLETED", completed_at="2026-04-01T10:00:00+00:00"))
    db.insert_job(_make_job("f1", "hf1", "FAILED"))
    db.insert_job(_make_job("f2", "hf2", "FAILED"))

    body = tc.get("/status").json()
    assert body["total_docs"] == 1
    assert body["pending_jobs"] == 0


def test_percent_indexed_and_failures(client):
    tc, db_path = client
    db = SQLiteDB(db_path=db_path)
    db.insert_job(_make_job("c1", "hc1", "COMPLETED", completed_at="2026-04-01T10:00:00+00:00"))
    db.insert_job(_make_job("c2", "hc2", "COMPLETED", completed_at="2026-04-02T10:00:00+00:00", file_type="image"))
    db.insert_job(_make_job("c3", "hc3", "COMPLETED", completed_at="2026-04-03T10:00:00+00:00", file_type="image"))
    db.insert_job(_make_job("f1", "hf1", "FAILED"))

    body = tc.get("/status").json()
    assert body["total_files"] == 4
    assert body["failed_docs"] == 1
    assert body["percent_indexed"] == 75
    assert body["by_type"] == {"pdf": 1, "image": 2}


def test_failed_then_reindexed_path_is_not_counted_as_failed(client):
    tc, db_path = client
    db = SQLiteDB(db_path=db_path)
    db.insert_job(_make_job("old", "h-old", "FAILED", path="/tmp/history"))
    db.insert_job(_make_job("new", "h-new", "COMPLETED", completed_at="2026-04-05T10:00:00+00:00", path="/tmp/history"))

    body = tc.get("/status").json()
    assert body["total_files"] == 1
    assert body["failed_docs"] == 0
    assert body["percent_indexed"] == 100


def test_services_all_up(client, monkeypatch):
    from unittest.mock import MagicMock, patch

    tc, _ = client
    monkeypatch.setenv("OLLAMA_MODEL", "llama3:8b")
    tags = MagicMock()
    tags.json.return_value = {"models": [{"name": "llama3:8b"}, {"name": "llama3.2:3b"}]}
    with patch("api.status.count", return_value=3), patch("api.status.requests.get", return_value=tags):
        body = tc.get("/status/services").json()
    assert body == {"api": True, "vector_store": True, "ollama": True,
                    "ollama_model": "llama3:8b", "ollama_model_ready": True}


def test_services_report_missing_model_and_down_store(client, monkeypatch):
    from unittest.mock import MagicMock, patch

    tc, _ = client
    monkeypatch.setenv("OLLAMA_MODEL", "llama3:8b")
    tags = MagicMock()
    tags.json.return_value = {"models": [{"name": "llama3.2:3b"}]}
    with patch("api.status.count", side_effect=RuntimeError("chroma down")), \
         patch("api.status.requests.get", return_value=tags):
        body = tc.get("/status/services").json()
    assert body["vector_store"] is False
    assert body["ollama"] is True
    assert body["ollama_model_ready"] is False


def test_services_report_ollama_down(client):
    from unittest.mock import patch

    import requests

    tc, _ = client
    with patch("api.status.count", return_value=0), \
         patch("api.status.requests.get", side_effect=requests.exceptions.ConnectionError("refused")):
        body = tc.get("/status/services").json()
    assert body["ollama"] is False
    assert body["ollama_model_ready"] is False
