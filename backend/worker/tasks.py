import logging
import os
from datetime import datetime, timezone
from typing import Optional

import chromadb.errors
import redis.exceptions
import requests.exceptions
from celery.exceptions import SoftTimeLimitExceeded

from parsers.base import ParseError
from parsers.browser_history import parse_browser_history
from parsers.image import parse_image
from parsers.pdf import parse_pdf
from parsers.text import parse_txt
from services.db import SQLiteDB
from services.embedding import EmbeddingService
from services.graph import KnowledgeGraph
from services.ner import NERService
from services.vector_store import VectorStore
from worker.celery_app import celery_app


logger = logging.getLogger(__name__)


# Module-level singletons: loaded once per worker process, not per task.
_embedder: Optional[EmbeddingService] = None
_store: Optional[VectorStore] = None
_db: Optional[SQLiteDB] = None
_ner: Optional[NERService] = None


def _services():
    global _embedder, _store, _db, _ner
    if _embedder is None:
        _embedder = EmbeddingService()
    if _store is None:
        _store = VectorStore()
    if _db is None:
        _db = SQLiteDB()
    if _ner is None:
        _ner = NERService()
    return _embedder, _store, _db, _ner


TRANSIENT_EXCEPTIONS = (
    redis.exceptions.RedisError,
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    chromadb.errors.ChromaError,
)


def _get_parser(file_type: str):
    parsers = {
        "pdf": parse_pdf,
        "txt": parse_txt,
        "image": parse_image,
        "browser_history": parse_browser_history,
    }
    parser = parsers.get(file_type)
    if parser is None:
        raise ValueError(f"Unsupported file type: {file_type}")
    return parser


@celery_app.task(bind=True, name="ingest_task", max_retries=3)
def ingest_task(self, job_id: str):
    embedder, store, db, ner = _services()
    job = db.get_job(job_id)
    if job is None:
        logger.error("Job not found: %s", job_id)
        return

    try:
        db.update_status(job_id, "PROCESSING")

        # The parser does both parsing and chunking in a single call. The
        # CHUNKING state is set AFTER it returns to reflect
        # "chunking just completed, embedding is next."
        parser = _get_parser(job["file_type"])
        chunks = parser(job["file_path"])
        if not chunks:
            raise ValueError("Parser returned zero chunks")
        db.update_status(job_id, "CHUNKING")

        vectors = embedder.embed_batch([c.content for c in chunks])
        db.update_status(job_id, "EMBEDDING")

        last_modified = datetime.fromtimestamp(
            os.path.getmtime(job["file_path"]), tz=timezone.utc
        ).isoformat()
        # Parser-supplied metadata (e.g. a browser visit's own timestamp and url)
        # overrides the file-level defaults; source_path and file_type always win.
        metadatas = [
            {
                "chunk_index": c.chunk_index,
                "last_modified": last_modified,
                **c.metadata,
                "source_path": job["file_path"],
                "file_type": job["file_type"],
            }
            for c in chunks
        ]

        # A new job for an already-indexed path (re-imported browser history, an
        # edited file) replaces that path's chunks instead of duplicating them.
        store.delete(job["file_path"])
        store.add(chunks, vectors, metadatas)

        # Entity extraction and knowledge-graph update.
        # NER runs outside the lock to minimize lock hold time.
        is_browser_history = job["file_type"] == "browser_history"
        # Browser visits: extract from the page title only. The URL half of the
        # chunk text only adds junk entities ("linkedin.com" as a place).
        chunk_entities = [
            (c, ner.extract(c.metadata["title"], source="title")
             if is_browser_history and c.metadata.get("title")
             else ner.extract(c.content))
            for c in chunks
        ]

        with KnowledgeGraph().locked() as kg:
            # Re-ingesting replaces the file's chunks above; replace its graph
            # contribution too, so mentions and co-occurrences aren't counted twice.
            kg.remove_document(job["file_path"])
            if is_browser_history:
                # For browser history: link per chunk (visit), not per file.
                for _chunk, entities in chunk_entities:
                    if entities:
                        ids = [kg.upsert_entity(name, etype, job["file_path"])
                               for name, etype in entities]
                        kg.link_cooccurring(ids, job["file_path"])
            else:
                all_ids = []
                for _chunk, entities in chunk_entities:
                    for name, etype in entities:
                        all_ids.append(
                            kg.upsert_entity(name, etype, job["file_path"])
                        )
                if all_ids:
                    kg.link_cooccurring(all_ids, job["file_path"])

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
