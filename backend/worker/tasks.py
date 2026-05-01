import logging
import os
from datetime import datetime, timezone
from typing import Optional

import chromadb.errors
import redis.exceptions
import requests.exceptions
from celery.exceptions import SoftTimeLimitExceeded

from parsers.base import ParseError
from parsers.pdf import parse_pdf
from services.db import SQLiteDB
from services.embedding import EmbeddingService
from services.vector_store import VectorStore
from worker.celery_app import celery_app


logger = logging.getLogger(__name__)


# Module-level singletons: loaded once per worker process, not per task.
_embedder: Optional[EmbeddingService] = None
_store: Optional[VectorStore] = None
_db: Optional[SQLiteDB] = None


def _services():
    global _embedder, _store, _db
    if _embedder is None:
        _embedder = EmbeddingService()
    if _store is None:
        _store = VectorStore()
    if _db is None:
        _db = SQLiteDB()
    return _embedder, _store, _db


TRANSIENT_EXCEPTIONS = (
    redis.exceptions.RedisError,
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    chromadb.errors.ChromaError,
)


@celery_app.task(bind=True, name="ingest_task", max_retries=3)
def ingest_task(self, job_id: str):
    embedder, store, db = _services()
    job = db.get_job(job_id)
    if job is None:
        logger.error("Job not found: %s", job_id)
        return

    try:
        db.update_status(job_id, "PROCESSING")

        # parse_pdf does both parsing and chunking in a single call. The
        # CHUNKING state is set AFTER parse_pdf returns to reflect
        # "chunking just completed, embedding is next."
        chunks = parse_pdf(job["file_path"])
        if not chunks:
            raise ValueError("Parser returned zero chunks")
        db.update_status(job_id, "CHUNKING")

        vectors = embedder.embed_batch([c.content for c in chunks])
        db.update_status(job_id, "EMBEDDING")

        last_modified = datetime.fromtimestamp(
            os.path.getmtime(job["file_path"]), tz=timezone.utc
        ).isoformat()
        metadatas = [
            {
                "source_path": job["file_path"],
                "file_type": job["file_type"],
                "chunk_index": c.chunk_index,
                "last_modified": last_modified,
            }
            for c in chunks
        ]

        store.add(chunks, vectors, metadatas)

        db.update_status(
            job_id,
            "COMPLETED",
            chunk_count=len(chunks),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    except TRANSIENT_EXCEPTIONS as e:
        retry_count = (job.get("retry_count") or 0) + 1
        db.update_status(
            job_id,
            "PENDING",
            retry_count=retry_count,
            error_message=str(e),
        )
        logger.warning(
            "Transient error on job %s, retry %d: %s", job_id, retry_count, e
        )
        # self.retry raises celery.exceptions.Retry, which propagates UP to
        # Celery — it does NOT match the bare `except Exception` clause below.
        # Sibling except clauses do not catch each other's raises.
        raise self.retry(exc=e, countdown=2 ** retry_count, max_retries=3)

    except (FileNotFoundError, ParseError, ValueError, SoftTimeLimitExceeded) as e:
        db.update_status(
            job_id, "FAILED", error_message=f"{type(e).__name__}: {e}"
        )
        logger.exception("Permanent error on job %s", job_id)

    except Exception as e:
        db.update_status(
            job_id, "FAILED", error_message=f"{type(e).__name__}: {e}"
        )
        logger.exception("Unhandled error on job %s", job_id)
