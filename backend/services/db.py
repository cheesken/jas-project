import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional


VALID_UPDATE_COLUMNS = {"error_message", "chunk_count", "retry_count", "completed_at"}

IN_FLIGHT_STATUSES = ("PENDING", "PROCESSING", "CHUNKING", "EMBEDDING")

_INSERT_COLUMNS = (
    "job_id",
    "file_path",
    "file_name",
    "file_type",
    "file_size",
    "file_hash",
    "status",
    "error_message",
    "chunk_count",
    "retry_count",
    "created_at",
    "updated_at",
    "completed_at",
)


class SQLiteDB:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or os.environ["SQLITE_PATH"]
        self._conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=10,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id        TEXT PRIMARY KEY,
                file_path     TEXT NOT NULL,
                file_name     TEXT NOT NULL,
                file_type     TEXT NOT NULL,
                file_size     INTEGER NOT NULL,
                file_hash     TEXT NOT NULL UNIQUE,
                status        TEXT NOT NULL,
                error_message TEXT,
                chunk_count   INTEGER DEFAULT 0,
                retry_count   INTEGER DEFAULT 0,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL,
                completed_at  TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_file_hash ON jobs(file_hash)")

    def insert_job(self, job: dict) -> None:
        row = (
            job["job_id"],
            job["file_path"],
            job["file_name"],
            job["file_type"],
            job["file_size"],
            job["file_hash"],
            job["status"],
            job.get("error_message"),
            job.get("chunk_count", 0) or 0,
            job.get("retry_count", 0) or 0,
            job["created_at"],
            job["updated_at"],
            job.get("completed_at"),
        )
        placeholders = ", ".join(["?"] * len(_INSERT_COLUMNS))
        columns = ", ".join(_INSERT_COLUMNS)
        self._conn.execute(
            f"INSERT INTO jobs ({columns}) VALUES ({placeholders})",
            row,
        )

    def update_status(self, job_id: str, status: str, **kwargs) -> None:
        unknown = set(kwargs) - VALID_UPDATE_COLUMNS
        if unknown:
            raise ValueError(f"Invalid update columns: {sorted(unknown)}")

        assignments = ["status = ?", "updated_at = ?"]
        values: list = [status, datetime.now(timezone.utc).isoformat()]
        for column, value in kwargs.items():
            assignments.append(f"{column} = ?")
            values.append(value)
        values.append(job_id)

        self._conn.execute(
            f"UPDATE jobs SET {', '.join(assignments)} WHERE job_id = ?",
            values,
        )

    def get_job(self, job_id: str) -> Optional[dict]:
        cur = self._conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        row = cur.fetchone()
        return dict(row) if row is not None else None

    def get_job_by_hash(self, file_hash: str) -> Optional[dict]:
        cur = self._conn.execute("SELECT * FROM jobs WHERE file_hash = ?", (file_hash,))
        row = cur.fetchone()
        return dict(row) if row is not None else None

    def get_all_jobs(self) -> List[dict]:
        cur = self._conn.execute("SELECT * FROM jobs ORDER BY created_at DESC")
        return [dict(row) for row in cur.fetchall()]

    def get_status_summary(self) -> dict:
        cur = self._conn.execute(
            "SELECT COUNT(*) AS c, MAX(completed_at) AS m FROM jobs WHERE status = 'COMPLETED'"
        )
        row = cur.fetchone()
        total_docs = row["c"] if row else 0
        last_updated = row["m"] if row else None

        placeholders = ", ".join(["?"] * len(IN_FLIGHT_STATUSES))
        cur = self._conn.execute(
            f"SELECT COUNT(*) AS c FROM jobs WHERE status IN ({placeholders})",
            IN_FLIGHT_STATUSES,
        )
        pending_jobs = cur.fetchone()["c"]

        return {
            "total_docs": total_docs,
            "last_updated": last_updated,
            "pending_jobs": pending_jobs,
        }
