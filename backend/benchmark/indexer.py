"""
Index a benchmark corpus with the production pipeline, into a throwaway store.

Points SQLite, ChromaDB and the knowledge graph at a work directory, then runs
the real `ingest_task` (parse, chunk, embed, store, NER, graph) in-process for
every file, so the benchmark measures the code the app runs. Must be called
before anything imports services that read these settings.
"""
import hashlib
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List

FILE_TYPES = {"notes": "txt", "emails": "txt", "docs": "pdf"}


def use_work_dir(work_dir: str) -> None:
    os.makedirs(work_dir, exist_ok=True)
    os.environ.pop("CHROMA_HOST", None)  # embedded Chroma, never the live server
    os.environ["CHROMA_PATH"] = os.path.join(work_dir, "chroma")
    os.environ["SQLITE_PATH"] = os.path.join(work_dir, "bench.db")
    os.environ["KG_PATH"] = os.path.join(work_dir, "kg.json")
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")


def corpus_files(corpus_dir: str) -> List[tuple]:
    files = []
    for folder, file_type in FILE_TYPES.items():
        for name in sorted(os.listdir(os.path.join(corpus_dir, folder))):
            files.append((os.path.join(corpus_dir, folder, name), file_type))
    files.append((os.path.join(corpus_dir, "browser", "History"), "browser_history"))
    return files


def index_corpus(corpus_dir: str) -> Dict[str, float]:
    from services.db import SQLiteDB
    from worker.tasks import ingest_task

    db = SQLiteDB()
    started = time.perf_counter()
    failed = []
    for path, file_type in corpus_files(corpus_dir):
        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        db.insert_job({"job_id": job_id, "file_path": path, "file_name": os.path.basename(path),
                       "file_type": file_type, "file_size": os.path.getsize(path), "file_hash": digest,
                       "status": "PENDING", "created_at": now, "updated_at": now})
        ingest_task(job_id)  # runs synchronously in this process
        job = db.get_job(job_id)
        if job["status"] != "COMPLETED":
            failed.append((path, job.get("error_message")))
    if failed:
        raise RuntimeError(f"{len(failed)} files failed to index, e.g. {failed[:3]}")
    return {"files": len(corpus_files(corpus_dir)), "seconds": time.perf_counter() - started}
