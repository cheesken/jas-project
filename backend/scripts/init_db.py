"""
Initialize the SQLite database for the personal memory system.

Usage:
    python scripts/init_db.py

Reads the database path from SQLITE_PATH (default: ./personal_memory.db).
Creates the parent directory if it does not exist.
Idempotent: running multiple times is safe.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.db import SQLiteDB


def main():
    db_path = os.environ.get("SQLITE_PATH", "./personal_memory.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    SQLiteDB(db_path=db_path)
    print(f"Database initialized at {db_path}")


if __name__ == "__main__":
    main()
