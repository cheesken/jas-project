"""
Remove a file from the index so it can be uploaded again as new (e.g. to rehearse
a live upload in a demo). Deletes its chunks from ChromaDB, its contribution to
the knowledge graph, and its job rows. The file itself is not touched.

Usage (no rebuild needed, reads the script from stdin):
    docker compose exec -T worker python - /absolute/path/to/file < backend/scripts/forget_file.py
"""
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent) if "__file__" in globals() else "/app")

from services.db import SQLiteDB
from services.graph import KnowledgeGraph
from services.vector_store import VectorStore


def forget(path: str) -> None:
    db = SQLiteDB()
    jobs = db._conn.execute("SELECT COUNT(*) FROM jobs WHERE file_path = ?", (path,)).fetchone()[0]
    VectorStore().delete(path)
    with KnowledgeGraph().locked() as kg:
        graph_changed = kg.remove_document(path)
    db._conn.execute("DELETE FROM jobs WHERE file_path = ?", (path,))
    print(f"Forgot {path}: {jobs} job row(s) removed, chunks deleted, graph {'updated' if graph_changed else 'unchanged'}.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: forget_file.py /absolute/path/to/file")
    forget(sys.argv[1])
