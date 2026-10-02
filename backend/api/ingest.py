import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.db import IN_FLIGHT_STATUSES, SQLiteDB
from worker.tasks import ingest_task

router = APIRouter()

# A job "in flight" longer than this lost its task (e.g. Docker stopped mid-job;
# Redis doesn't persist the queue). The worker's hard time limit is 10 minutes.
STALE_AFTER = timedelta(minutes=15)


class IngestRequest(BaseModel):
    file_path: str
    file_type: Literal["pdf", "txt", "image", "browser_history"]
    # Re-run an unchanged, already-indexed file instead of returning 409, e.g. to
    # pick up entities for files indexed before NER existed.
    force: bool = False


class IngestResponse(BaseModel):
    job_id: str
    status: str


class ReindexResponse(BaseModel):
    queued: int
    skipped: int


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    error_message: str | None = None
    chunk_count: int = 0


def _compute_hash(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            block = f.read(65536)  # 64 KB
            if not block:
                break
            h.update(block)
    return h.hexdigest()


@router.post("/ingest", status_code=201, response_model=IngestResponse)
def ingest_file(req: IngestRequest):
    if not os.path.isfile(req.file_path):
        raise HTTPException(status_code=400, detail="File not found at path")

    file_hash = _compute_hash(req.file_path)

    db = SQLiteDB()
    existing = db.get_job_by_hash(file_hash)
    if existing and req.force and existing["file_path"] == req.file_path:
        if _in_flight(existing):
            raise HTTPException(
                status_code=409,
                detail={"message": "File is already being indexed", "existing_job_id": existing["job_id"]},
            )
        _requeue(db, existing["job_id"])
        return IngestResponse(job_id=existing["job_id"], status="PENDING")
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"message": "File already ingested", "existing_job_id": existing["job_id"]},
        )

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db.insert_job({
        "job_id": job_id,
        "file_path": req.file_path,
        "file_name": os.path.basename(req.file_path),
        "file_type": req.file_type,
        "file_size": os.path.getsize(req.file_path),
        "file_hash": file_hash,
        "status": "PENDING",
        "created_at": now,
        "updated_at": now,
    })

    ingest_task.delay(job_id)

    return IngestResponse(job_id=job_id, status="PENDING")


def _in_flight(job: dict) -> bool:
    if job["status"] not in IN_FLIGHT_STATUSES:
        return False
    try:
        updated = datetime.fromisoformat(job["updated_at"])
    except (KeyError, TypeError, ValueError):
        return True
    return datetime.now(timezone.utc) - updated < STALE_AFTER


def _requeue(db: SQLiteDB, job_id: str) -> None:
    # file_hash is UNIQUE, so a re-run reuses the job row instead of inserting a new one.
    db.update_status(job_id, "PENDING", retry_count=0, error_message=None, chunk_count=0, completed_at=None)
    ingest_task.delay(job_id)


@router.post("/reindex", status_code=202, response_model=ReindexResponse)
def reindex_all():
    """Re-run ingestion for every indexed file that still exists.

    Rebuilds chunks and knowledge-graph entities, e.g. after NER was added or
    changed. Each path is queued once (its newest job); jobs still in flight
    and files that no longer exist are skipped. A job stuck in flight longer
    than STALE_AFTER is treated as lost and re-queued.
    """
    db = SQLiteDB()
    seen = set()
    queued = skipped = 0
    for job in db.get_all_jobs():  # newest first
        path = job["file_path"]
        if path in seen:
            continue
        seen.add(path)
        if _in_flight(job) or not os.path.isfile(path):
            skipped += 1
            continue
        _requeue(db, job["job_id"])
        queued += 1
    return ReindexResponse(queued=queued, skipped=skipped)


@router.get("/ingest/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    db = SQLiteDB()
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        error_message=job.get("error_message"),
        chunk_count=job.get("chunk_count", 0),
    )
