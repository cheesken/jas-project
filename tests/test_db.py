import sqlite3
import threading
from datetime import datetime, timezone

import pytest

from services.db import SQLiteDB


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_job(job_id="j1", file_hash="hash1", status="PENDING", **overrides) -> dict:
    job = {
        "job_id": job_id,
        "file_path": f"/tmp/{job_id}.pdf",
        "file_name": f"{job_id}.pdf",
        "file_type": "pdf",
        "file_size": 1024,
        "file_hash": file_hash,
        "status": status,
        "error_message": None,
        "chunk_count": 0,
        "retry_count": 0,
        "created_at": _now(),
        "updated_at": _now(),
        "completed_at": None,
    }
    job.update(overrides)
    return job


@pytest.fixture
def db(tmp_path):
    return SQLiteDB(db_path=str(tmp_path / "test.db"))


def test_init_creates_table_and_indexes(db):
    cur = db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'index')"
    )
    names = {row["name"] for row in cur.fetchall()}
    assert "jobs" in names
    assert "idx_jobs_status" in names
    assert "idx_jobs_file_hash" in names


def test_insert_and_get_job_roundtrip(db):
    job = _make_job()
    db.insert_job(job)
    fetched = db.get_job("j1")
    assert fetched is not None
    assert fetched["job_id"] == "j1"
    assert fetched["file_hash"] == "hash1"
    assert fetched["status"] == "PENDING"
    assert fetched["chunk_count"] == 0


def test_insert_duplicate_hash_raises(db):
    db.insert_job(_make_job(job_id="j1", file_hash="dup"))
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_job(_make_job(job_id="j2", file_hash="dup"))


def test_update_status_only_changes_status_and_updated_at(db):
    db.insert_job(_make_job())
    before = db.get_job("j1")
    db.update_status("j1", "PROCESSING")
    after = db.get_job("j1")
    assert after["status"] == "PROCESSING"
    assert after["updated_at"] != before["updated_at"]
    assert after["chunk_count"] == before["chunk_count"]
    assert after["error_message"] == before["error_message"]


def test_update_status_with_kwargs(db):
    db.insert_job(_make_job())
    completed = "2026-05-01T12:00:00+00:00"
    db.update_status("j1", "COMPLETED", chunk_count=12, completed_at=completed)
    row = db.get_job("j1")
    assert row["status"] == "COMPLETED"
    assert row["chunk_count"] == 12
    assert row["completed_at"] == completed


def test_update_status_rejects_unknown_kwarg(db):
    db.insert_job(_make_job())
    with pytest.raises(ValueError):
        db.update_status("j1", "FAILED", bogus_field="x")


def test_get_job_returns_none_for_missing(db):
    assert db.get_job("nope") is None


def test_get_job_by_hash(db):
    db.insert_job(_make_job(job_id="j1", file_hash="abc"))
    assert db.get_job_by_hash("abc")["job_id"] == "j1"
    assert db.get_job_by_hash("missing") is None


def test_get_all_jobs_orders_by_created_at_desc(db):
    db.insert_job(_make_job(job_id="old", file_hash="h_old", created_at="2026-01-01T00:00:00+00:00"))
    db.insert_job(_make_job(job_id="new", file_hash="h_new", created_at="2026-05-01T00:00:00+00:00"))
    db.insert_job(_make_job(job_id="mid", file_hash="h_mid", created_at="2026-03-01T00:00:00+00:00"))
    rows = db.get_all_jobs()
    assert [r["job_id"] for r in rows] == ["new", "mid", "old"]


def test_get_status_summary(db):
    db.insert_job(_make_job(
        job_id="c1", file_hash="hc1", status="COMPLETED",
        completed_at="2026-04-01T10:00:00+00:00",
    ))
    db.insert_job(_make_job(
        job_id="c2", file_hash="hc2", status="COMPLETED",
        completed_at="2026-04-15T10:00:00+00:00",
    ))
    db.insert_job(_make_job(job_id="p1", file_hash="hp1", status="PENDING"))
    db.insert_job(_make_job(job_id="p2", file_hash="hp2", status="PROCESSING"))
    db.insert_job(_make_job(job_id="p3", file_hash="hp3", status="CHUNKING"))
    db.insert_job(_make_job(job_id="p4", file_hash="hp4", status="EMBEDDING"))
    db.insert_job(_make_job(job_id="f1", file_hash="hf1", status="FAILED"))

    summary = db.get_status_summary()
    assert summary["total_docs"] == 2
    assert summary["last_updated"] == "2026-04-15T10:00:00+00:00"
    assert summary["pending_jobs"] == 4


def test_concurrent_read_write_does_not_deadlock(tmp_path):
    db_path = str(tmp_path / "wal.db")
    writer = SQLiteDB(db_path=db_path)
    reader = SQLiteDB(db_path=db_path)
    writer.insert_job(_make_job())

    errors: list = []
    done = threading.Event()

    def reader_loop():
        try:
            for _ in range(20):
                _ = reader.get_job("j1")
        except Exception as exc:
            errors.append(exc)
        finally:
            done.set()

    t = threading.Thread(target=reader_loop)
    t.start()
    for i in range(20):
        writer.update_status("j1", "PROCESSING" if i % 2 == 0 else "PENDING")
    t.join(timeout=5)
    assert done.is_set()
    assert not errors
