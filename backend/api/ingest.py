import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from parsers.browser_history import SAFARI_PERMISSION_HINT

from services.db import IN_FLIGHT_STATUSES, SQLiteDB
from services.graph import KnowledgeGraph
from services.vector_store import VectorStore
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


class DeleteResponse(BaseModel):
    file_path: str
    jobs_removed: int


class IndexedFile(BaseModel):
    job_id: str
    file_name: str
    file_type: str
    status: str
    error_message: str | None = None
    completed_at: str | None = None


class IndexedFilesResponse(BaseModel):
    files: list[IndexedFile]


class ClearResponse(BaseModel):
    files_removed: int


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
        # Without Full Disk Access, macOS hides ~/Library/Safari from Docker
        # entirely, so a Safari history path the desktop app just found on the
        # host looks missing here. Explain the permission rather than "not found".
        if "/Library/Safari/" in req.file_path:
            raise HTTPException(status_code=403, detail=SAFARI_PERMISSION_HINT)
        raise HTTPException(status_code=400, detail="File not found at path")

    try:
        file_hash = _compute_hash(req.file_path)
    except PermissionError:
        # The file exists but macOS won't let Docker read it (e.g. Safari history
        # without Full Disk Access). Say so instead of failing with a 500.
        hint = SAFARI_PERMISSION_HINT if "/Safari/" in req.file_path else "Permission denied reading the file"
        raise HTTPException(status_code=403, detail=hint)

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


@router.delete("/ingest/{job_id}", response_model=DeleteResponse)
def delete_indexed_file(job_id: str):
    """Remove a job's file from the index: its chunks, its knowledge-graph
    contribution and every job row for that path. The file itself is untouched,
    and uploading it again indexes it as new."""
    db = SQLiteDB()
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if _in_flight(job):
        raise HTTPException(status_code=409, detail="File is still being indexed")
    path = job["file_path"]
    return DeleteResponse(file_path=path, jobs_removed=_forget_path(db, path))


def _forget_path(db: SQLiteDB, path: str) -> int:
    VectorStore().delete(path)
    with KnowledgeGraph().locked() as kg:
        kg.remove_document(path)
    return db.delete_jobs_for_path(path)


@router.get("/ingest", response_model=IndexedFilesResponse)
def list_indexed_files():
    return IndexedFilesResponse(files=[IndexedFile(**f) for f in SQLiteDB().get_indexed_files()])


@router.delete("/ingest", response_model=ClearResponse)
def clear_index():
    db = SQLiteDB()
    files = db.get_indexed_files()
    if any(_in_flight(f) for f in files):
        raise HTTPException(status_code=409, detail="Files are still being indexed; try again when they finish")
    for f in files:
        _forget_path(db, f["file_path"])
    return ClearResponse(files_removed=len(files))


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
