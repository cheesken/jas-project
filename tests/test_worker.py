from unittest.mock import MagicMock, patch

import chromadb.errors
import pytest
import redis.exceptions
from celery.exceptions import Retry

import worker.tasks as tasks_module
from parsers.base import Chunk, ParseError


@pytest.fixture(autouse=True)
def eager_celery():
    from worker.celery_app import celery_app
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False


@pytest.fixture(autouse=True)
def reset_singletons():
    tasks_module._embedder = None
    tasks_module._store = None
    tasks_module._db = None
    yield
    tasks_module._embedder = None
    tasks_module._store = None
    tasks_module._db = None


def _chunk(idx: int) -> Chunk:
    return Chunk(
        id=f"c{idx}",
        content=f"chunk {idx} text",
        token_count=10,
        chunk_index=idx,
        start_char=0,
        end_char=10,
        page_number=1,
    )


def _seed_job(db, job_id="job-1", retry_count=0):
    db.get_job.return_value = {
        "job_id": job_id,
        "file_path": "/tmp/sample.pdf",
        "file_name": "sample.pdf",
        "file_type": "pdf",
        "file_size": 1024,
        "file_hash": "h",
        "status": "PENDING",
        "error_message": None,
        "chunk_count": 0,
        "retry_count": retry_count,
        "created_at": "2026-05-01T00:00:00+00:00",
        "updated_at": "2026-05-01T00:00:00+00:00",
        "completed_at": None,
    }


def _patch_services(db, embedder, store):
    return patch.multiple(
        tasks_module,
        _db=db,
        _store=store,
        _embedder=embedder,
    )


def _statuses(db):
    return [call.args[1] for call in db.update_status.call_args_list]


def test_happy_path_runs_full_state_machine():
    db = MagicMock()
    embedder = MagicMock()
    store = MagicMock()
    _seed_job(db)
    chunks = [_chunk(0), _chunk(1), _chunk(2)]
    vectors = [[0.0] * 384 for _ in chunks]
    embedder.embed_batch.return_value = vectors

    with patch("worker.tasks.parse_pdf", return_value=chunks), \
         patch("worker.tasks.os.path.getmtime", return_value=1714521600.0), \
         _patch_services(db, embedder, store):
        tasks_module.ingest_task.apply(args=["job-1"]).get()

    assert _statuses(db) == ["PROCESSING", "CHUNKING", "EMBEDDING", "COMPLETED"]
    final_call = db.update_status.call_args_list[-1]
    assert final_call.args == ("job-1", "COMPLETED")
    assert final_call.kwargs["chunk_count"] == 3
    assert "completed_at" in final_call.kwargs
    store.add.assert_called_once()


def test_file_not_found_marks_failed_no_retry():
    db = MagicMock()
    embedder = MagicMock()
    store = MagicMock()
    _seed_job(db)

    with patch("worker.tasks.parse_pdf", side_effect=FileNotFoundError("missing.pdf")), \
         _patch_services(db, embedder, store):
        tasks_module.ingest_task.apply(args=["job-1"]).get()

    statuses = _statuses(db)
    assert statuses[-1] == "FAILED"
    assert "FileNotFoundError" in db.update_status.call_args_list[-1].kwargs["error_message"]
    assert "PENDING" not in statuses[1:]  # no retry-induced PENDING transition


def test_parse_error_marks_failed():
    db = MagicMock()
    embedder = MagicMock()
    store = MagicMock()
    _seed_job(db)

    with patch("worker.tasks.parse_pdf", side_effect=ParseError("bad pdf")), \
         _patch_services(db, embedder, store):
        tasks_module.ingest_task.apply(args=["job-1"]).get()

    last = db.update_status.call_args_list[-1]
    assert last.args[1] == "FAILED"
    assert "ParseError" in last.kwargs["error_message"]


def test_empty_chunks_marks_failed_with_value_error():
    db = MagicMock()
    embedder = MagicMock()
    store = MagicMock()
    _seed_job(db)

    with patch("worker.tasks.parse_pdf", return_value=[]), \
         _patch_services(db, embedder, store):
        tasks_module.ingest_task.apply(args=["job-1"]).get()

    last = db.update_status.call_args_list[-1]
    assert last.args[1] == "FAILED"
    assert "ValueError" in last.kwargs["error_message"]


def test_transient_redis_error_triggers_retry():
    db = MagicMock()
    embedder = MagicMock()
    store = MagicMock()
    _seed_job(db, retry_count=0)

    embedder.embed_batch.side_effect = redis.exceptions.RedisError("simulated")

    with patch("worker.tasks.parse_pdf", return_value=[_chunk(0)]), \
         _patch_services(db, embedder, store), \
         pytest.raises(Retry):
        tasks_module.ingest_task.apply(args=["job-1"]).get()

    pending_calls = [
        call for call in db.update_status.call_args_list
        if call.args[1] == "PENDING"
    ]
    assert len(pending_calls) == 1
    assert pending_calls[0].kwargs["retry_count"] == 1
    assert "simulated" in pending_calls[0].kwargs["error_message"]


def test_missing_job_logs_and_returns():
    db = MagicMock()
    embedder = MagicMock()
    store = MagicMock()
    db.get_job.return_value = None

    with _patch_services(db, embedder, store):
        result = tasks_module.ingest_task.apply(args=["nope"]).get()

    assert result is None
    db.update_status.assert_not_called()


def test_chunk_count_persisted_correctly():
    db = MagicMock()
    embedder = MagicMock()
    store = MagicMock()
    _seed_job(db)
    chunks = [_chunk(i) for i in range(7)]
    embedder.embed_batch.return_value = [[0.0] * 384 for _ in chunks]

    with patch("worker.tasks.parse_pdf", return_value=chunks), \
         patch("worker.tasks.os.path.getmtime", return_value=1714521600.0), \
         _patch_services(db, embedder, store):
        tasks_module.ingest_task.apply(args=["job-1"]).get()

    assert db.update_status.call_args_list[-1].kwargs["chunk_count"] == 7


def test_transient_chroma_error_triggers_retry():
    db = MagicMock()
    embedder = MagicMock()
    store = MagicMock()
    _seed_job(db, retry_count=0)

    chunks = [_chunk(0)]
    embedder.embed_batch.return_value = [[0.0] * 384]
    store.add.side_effect = chromadb.errors.ChromaError("simulated chroma failure")

    with patch("worker.tasks.parse_pdf", return_value=chunks), \
         patch("worker.tasks.os.path.getmtime", return_value=1714521600.0), \
         _patch_services(db, embedder, store), \
         pytest.raises(Retry):
        tasks_module.ingest_task.apply(args=["job-1"]).get()

    pending_calls = [
        call for call in db.update_status.call_args_list
        if call.args[1] == "PENDING"
    ]
    assert len(pending_calls) == 1
    assert pending_calls[0].kwargs["retry_count"] == 1
    assert "simulated chroma failure" in pending_calls[0].kwargs["error_message"]


def test_embedding_state_skipped_on_permanent_error_before_embed():
    db = MagicMock()
    embedder = MagicMock()
    store = MagicMock()
    _seed_job(db)
    embedder.embed_batch.side_effect = ValueError("bad embedding input")

    with patch("worker.tasks.parse_pdf", return_value=[_chunk(0)]), \
         _patch_services(db, embedder, store):
        tasks_module.ingest_task.apply(args=["job-1"]).get()

    statuses = _statuses(db)
    assert "EMBEDDING" not in statuses
    assert statuses[:2] == ["PROCESSING", "CHUNKING"]
    assert statuses[-1] == "FAILED"
