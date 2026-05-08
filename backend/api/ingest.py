import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.db import SQLiteDB
from worker.tasks import ingest_task

router = APIRouter()


class IngestRequest(BaseModel):
    file_path: str
    file_type: Literal["pdf"]


class IngestResponse(BaseModel):
    job_id: str
    status: str


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
