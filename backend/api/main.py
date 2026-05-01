import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.ingest import router as ingest_router
from api.query import router as query_router
from api.status import router as status_router
from services.db import SQLiteDB
from services.vector_store import VectorStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up: initializing SQLite and ChromaDB")

    sqlite_path = os.environ.get("SQLITE_PATH", "/data/personal_memory.db")
    Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    SQLiteDB(db_path=sqlite_path)

    chroma_path = os.environ.get("CHROMA_PATH", "/data/chroma")
    Path(chroma_path).mkdir(parents=True, exist_ok=True)
    # TODO(team): this creates a second chromadb.PersistentClient pointing at the same path
    # as the lazy singleton in services/query.py. Process-safe per §19, but wastes resources.
    # Clean fix: call count() here to warm the singleton instead of constructing VectorStore directly.
    VectorStore(persist_path=chroma_path)

    logger.info("Startup complete")
    yield
    logger.info("Shutting down")


app = FastAPI(title="Personal Memory API", version="0.1.0", lifespan=lifespan)

# CORS — local-only system, allow all origins. Electron renderer talks to localhost:8000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers mounted at root — no /api/v1 prefix per §10.
app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(status_router)


@app.get("/health")
def health():
    return {"status": "ok"}
